"""Per-user file storage on the shared data volume.

    /data/users/<user_id>/
        uploads/<upload_id>/<original filename>
        pages/<upload_id>/page_<i>.png
        exports/<file>.xlsx
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import USERS_DIR


def user_root(user_id: str) -> Path:
    return USERS_DIR / user_id


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_uploads(user_id: str) -> Path:
    return _ensure(user_root(user_id) / "uploads")


def user_pages(user_id: str) -> Path:
    return _ensure(user_root(user_id) / "pages")


def user_exports(user_id: str) -> Path:
    return _ensure(user_root(user_id) / "exports")


def delete_upload_files(user_id: str, upload_id: str) -> None:
    shutil.rmtree(user_uploads(user_id) / upload_id, ignore_errors=True)
    shutil.rmtree(user_pages(user_id) / upload_id, ignore_errors=True)


def delete_user_files(user_id: str) -> None:
    shutil.rmtree(user_root(user_id), ignore_errors=True)


def user_disk_usage(user_id: str) -> int:
    """Total bytes of this user's files (uploads + rendered pages + exports)."""
    root = user_root(user_id)
    if not root.exists():
        return 0
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def prune_exports(user_id: str, keep: int) -> None:
    """Delete all but the `keep` newest export files for a user."""
    files = sorted(
        (p for p in user_exports(user_id).iterdir() if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in files[keep:]:
        p.unlink(missing_ok=True)
