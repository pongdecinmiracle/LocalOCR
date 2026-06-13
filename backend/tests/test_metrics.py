from __future__ import annotations

import io

from conftest import register
from PIL import Image

from app import jobs


def _mock_ollama(monkeypatch, installed=None, loaded=None):
    monkeypatch.setattr("app.routers.admin.installed_models", lambda: installed)
    monkeypatch.setattr("app.routers.admin.loaded_models", lambda: loaded)


def test_metrics_requires_admin(client, second_client, monkeypatch):
    _mock_ollama(monkeypatch)
    register(client, "alice")          # admin
    register(second_client, "bob")     # regular user
    assert second_client.get("/api/admin/metrics").status_code == 403
    assert client.get("/api/admin/metrics").status_code == 200


def test_metrics_payload(client, monkeypatch):
    _mock_ollama(
        monkeypatch,
        installed=["qwen2.5vl:7b"],
        loaded=[{"name": "qwen2.5vl:7b", "size": 6_000_000_000, "size_vram": 6_000_000_000}],
    )
    register(client, "alice")
    m = client.get("/api/admin/metrics").json()

    assert 0 <= m["cpu"]["percent"] <= 100
    assert m["cpu"]["cores"] >= 1
    assert m["memory"]["total_mb"] > 0
    assert m["disk"]["total_mb"] > 0

    assert m["gpu"]["ollama_up"] is True
    mod = m["gpu"]["loaded_models"][0]
    assert mod["name"] == "qwen2.5vl:7b"
    assert mod["vram_mb"] == mod["size_mb"] > 0

    assert m["services"] == {"database": "ok", "ollama": "ok", "model": "ready"}
    assert m["errors"] == {
        "jobs_done_total": 0,
        "jobs_failed_total": 0,
        "jobs_failed_24h": 0,
        "recent_failures": [],
    }

    # Alice just made authenticated requests, so she counts as active.
    assert m["activity"]["active_users_5m"] >= 1
    assert m["activity"]["total_users"] == 1
    assert m["activity"]["jobs_queued"] == 0
    assert m["activity"]["jobs_running"] == 0


def test_metrics_reports_engine_down(client, monkeypatch):
    _mock_ollama(monkeypatch)  # both None -> unreachable
    register(client, "alice")
    m = client.get("/api/admin/metrics").json()
    assert m["gpu"]["ollama_up"] is False
    assert m["gpu"]["loaded_models"] == []
    assert m["services"]["ollama"] == "down"
    assert m["services"]["model"] == "unknown"


def test_metrics_lists_failed_jobs(client, monkeypatch):
    _mock_ollama(monkeypatch, installed=["qwen2.5vl:7b"])
    register(client, "alice")

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
    up = client.post(
        "/api/upload", files=[("files", ("doc.png", buf.getvalue(), "image/png"))]
    ).json()["uploads"][0]
    tid = client.post(
        "/api/templates",
        json={
            "name": "T",
            "fields": [
                {"name": "a", "type": "text", "page": 0, "box": {"x": 0, "y": 0, "w": 1, "h": 1}}
            ],
        },
    ).json()["id"]

    monkeypatch.setattr(
        "app.routers.extraction.installed_models", lambda: ["qwen2.5vl:7b"]
    )
    job = client.post(
        "/api/extract", json={"template_id": tid, "upload_ids": [up["upload_id"]]}
    ).json()

    def _boom(pages_dir, template, model):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(jobs, "extract_document", _boom)
    jobs.run_job(job["job_id"])

    m = client.get("/api/admin/metrics").json()
    assert m["errors"]["jobs_failed_24h"] == 1
    assert m["errors"]["jobs_failed_total"] == 1
    assert m["errors"]["jobs_done_total"] == 0
    failure = m["errors"]["recent_failures"][0]
    assert failure["username"] == "alice"
    assert "model exploded" in failure["error"]
    assert failure["documents"] == 1

    # A successful run moves the success counter.
    job2 = client.post(
        "/api/extract", json={"template_id": tid, "upload_ids": [up["upload_id"]]}
    ).json()
    monkeypatch.setattr(
        jobs, "extract_document", lambda pages_dir, template, model: {"fields": {"a": "x"}}
    )
    jobs.run_job(job2["job_id"])
    m = client.get("/api/admin/metrics").json()
    assert m["errors"]["jobs_done_total"] == 1
    assert m["errors"]["jobs_failed_total"] == 1
