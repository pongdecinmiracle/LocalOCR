from __future__ import annotations

import io
from pathlib import Path

import pytest
from conftest import register
from PIL import Image

from app import config
from app.routers.uploads import safe_filename


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_safe_filename_strips_directories():
    assert safe_filename("../../etc/passwd.png") == "passwd.png"
    assert safe_filename("..\\..\\windows\\evil.pdf") == "evil.pdf"
    assert safe_filename("nested/dir/scan.jpg") == "scan.jpg"


def test_safe_filename_rejects_disallowed_types():
    for bad in ("run.exe", "page.html", "noext", ".."):
        with pytest.raises(ValueError):
            safe_filename(bad)


def test_upload_with_traversal_filename_stays_in_user_dir(client):
    register(client)
    r = client.post(
        "/api/upload",
        files=[("files", ("../../../evil.png", _png_bytes(), "image/png"))],
    )
    assert r.status_code == 200
    up = r.json()["uploads"][0]
    assert up["filename"] == "evil.png"

    # The file must exist inside the per-user uploads tree and nowhere above it.
    stored = list(config.USERS_DIR.rglob("evil.png"))
    assert len(stored) == 1
    assert config.USERS_DIR in stored[0].parents
    assert not (config.DATA_DIR / "evil.png").exists()
    assert not Path(config.DATA_DIR.anchor, "evil.png").exists()


def test_upload_rejects_disallowed_extension(client):
    register(client)
    r = client.post(
        "/api/upload",
        files=[("files", ("script.svg", b"<svg/>", "image/svg+xml"))],
    )
    assert r.status_code == 400


def test_upload_quota_enforced(client, monkeypatch):
    register(client)
    monkeypatch.setattr(config, "USER_QUOTA_MB", 0)
    r = client.post(
        "/api/upload",
        files=[("files", ("doc.png", _png_bytes(), "image/png"))],
    )
    assert r.status_code == 413


def test_users_cannot_see_each_others_uploads(client, second_client):
    register(client, "alice")
    register(second_client, "bob")
    r = client.post(
        "/api/upload", files=[("files", ("mine.png", _png_bytes(), "image/png"))]
    )
    upload_id = r.json()["uploads"][0]["upload_id"]

    assert second_client.get("/api/uploads").json()["uploads"] == []
    assert second_client.get(f"/api/page/{upload_id}/0").status_code == 404
    assert client.get(f"/api/page/{upload_id}/0").status_code == 200
