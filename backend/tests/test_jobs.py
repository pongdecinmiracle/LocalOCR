from __future__ import annotations

import io

from conftest import register
from PIL import Image

from app import jobs


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
    return buf.getvalue()


def _make_template(client) -> str:
    r = client.post(
        "/api/templates",
        json={
            "name": "Invoice",
            "fields": [
                {
                    "name": "total",
                    "type": "number",
                    "page": 0,
                    "box": {"x": 0.7, "y": 0.8, "w": 0.2, "h": 0.05},
                }
            ],
        },
    )
    assert r.status_code == 200
    return r.json()["id"]


def test_extract_unknown_template_404(client):
    register(client)
    r = client.post("/api/extract", json={"template_id": "nope", "upload_ids": ["x"]})
    assert r.status_code == 404


def test_extract_requires_ollama(client, monkeypatch):
    register(client)
    tid = _make_template(client)
    monkeypatch.setattr("app.routers.extraction.installed_models", lambda: None)
    r = client.post("/api/extract", json={"template_id": tid, "upload_ids": ["x"]})
    assert r.status_code == 503


def test_job_lifecycle(client, monkeypatch):
    register(client)
    tid = _make_template(client)
    up = client.post(
        "/api/upload", files=[("files", ("doc.png", _png_bytes(), "image/png"))]
    ).json()["uploads"][0]

    monkeypatch.setattr(
        "app.routers.extraction.installed_models", lambda: ["qwen2.5vl:7b"]
    )
    r = client.post(
        "/api/extract", json={"template_id": tid, "upload_ids": [up["upload_id"], "bogus"]}
    )
    assert r.status_code == 200
    job = r.json()
    assert job["status"] == "queued"
    assert job["total"] == 1  # the bogus / unowned id was filtered out

    # Run the queued job synchronously with the model call stubbed out.
    monkeypatch.setattr(
        jobs, "extract_document", lambda pages_dir, template, model: {"fields": {"total": 42}}
    )
    jobs.run_job(job["job_id"])

    done = client.get(f"/api/extract/jobs/{job['job_id']}").json()
    assert done["status"] == "done"
    assert done["done"] == 1
    assert done["results"][0]["fields"] == {"total": 42}
    assert done["results"][0]["file"] == "doc.png"


def test_job_is_private(client, second_client, monkeypatch):
    register(client, "alice")
    register(second_client, "bob")
    tid = _make_template(client)
    up = client.post(
        "/api/upload", files=[("files", ("doc.png", _png_bytes(), "image/png"))]
    ).json()["uploads"][0]
    monkeypatch.setattr(
        "app.routers.extraction.installed_models", lambda: ["qwen2.5vl:7b"]
    )
    job = client.post(
        "/api/extract", json={"template_id": tid, "upload_ids": [up["upload_id"]]}
    ).json()
    assert second_client.get(f"/api/extract/jobs/{job['job_id']}").status_code == 404
