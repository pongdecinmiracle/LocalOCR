"""Upload documents, list/delete them, and serve rendered page images."""
from __future__ import annotations

import logging
import re
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.deps import current_user, get_db
from app.models import Upload
from app.pdf_utils import render_document
from app.storage import delete_upload_files, user_disk_usage, user_pages, user_uploads

log = logging.getLogger("localocr.uploads")

router = APIRouter(prefix="/api", tags=["uploads"])

_UNSAFE_CHARS = re.compile(r"[^\w.\- ()\[\]]")


def safe_filename(name: str) -> str:
    """Sanitize a client-supplied filename to a flat, safe basename.

    Strips any directory components (both / and \\), control/special
    characters, and enforces the upload extension allowlist.
    Raises ValueError if the file type is not allowed.
    """
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = _UNSAFE_CHARS.sub("_", base).strip(" .")
    ext = Path(base).suffix.lower()
    if ext not in config.ALLOWED_UPLOAD_EXTS:
        allowed = ", ".join(sorted(config.ALLOWED_UPLOAD_EXTS))
        raise ValueError(f"File type '{ext or 'unknown'}' is not allowed. Allowed: {allowed}")
    stem = Path(base).stem[:100] or "document"
    return f"{stem}{ext}"


@router.post("/upload")
async def upload(
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
    files: list[UploadFile] = File(...),
):
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    quota_bytes = config.USER_QUOTA_MB * 1024 * 1024
    usage = user_disk_usage(user["id"])

    out = []
    for f in files:
        try:
            fname = safe_filename(f.filename)
        except ValueError as e:
            raise HTTPException(400, str(e))

        if usage >= quota_bytes:
            raise HTTPException(
                413,
                f"Storage quota exceeded ({config.USER_QUOTA_MB} MB). "
                "Delete some documents and try again.",
            )

        upload_id = uuid.uuid4().hex[:12]
        dest_dir = user_uploads(user["id"]) / upload_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / fname
        pages_dir = user_pages(user["id"]) / upload_id

        size = 0
        try:
            with dest.open("wb") as buf:
                while chunk := await f.read(1 << 20):
                    size += len(chunk)
                    if size > max_bytes:
                        raise HTTPException(
                            413, f"'{fname}' exceeds the {config.MAX_UPLOAD_MB} MB per-file limit."
                        )
                    buf.write(chunk)

            pages = render_document(dest, pages_dir, max_pages=config.MAX_PAGES)
        except HTTPException:
            shutil.rmtree(dest_dir, ignore_errors=True)
            shutil.rmtree(pages_dir, ignore_errors=True)
            raise
        except Exception as e:
            shutil.rmtree(dest_dir, ignore_errors=True)
            shutil.rmtree(pages_dir, ignore_errors=True)
            raise HTTPException(400, f"Could not read '{fname}': {e}")

        usage += size
        for p in pages:
            p["url"] = f"/api/page/{upload_id}/{p['index']}"

        db.add(
            Upload(
                id=upload_id,
                user_id=user["id"],
                filename=fname,
                pages=pages,
                created_at=int(time.time()),
            )
        )
        db.commit()
        log.info("upload: user=%s id=%s file=%s pages=%d", user["id"], upload_id, fname, len(pages))
        out.append({"upload_id": upload_id, "filename": fname, "pages": pages})
    return {"uploads": out}


@router.get("/uploads")
def list_uploads(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Upload).where(Upload.user_id == user["id"]).order_by(Upload.created_at.desc())
    ).all()
    return {
        "uploads": [
            {"upload_id": r.id, "filename": r.filename, "pages": r.pages} for r in rows
        ]
    }


@router.delete("/uploads/{upload_id}")
def delete_upload(upload_id: str, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(Upload, upload_id)
    if row and row.user_id == user["id"]:
        db.delete(row)
        db.commit()
    delete_upload_files(user["id"], upload_id)
    return {"deleted": upload_id}


@router.get("/page/{upload_id}/{page_index}")
def page_image(
    upload_id: str, page_index: int, user: dict = Depends(current_user)
):
    png = user_pages(user["id"]) / upload_id / f"page_{page_index}.png"
    if not png.exists():
        raise HTTPException(404, "page not found")
    return FileResponse(png, media_type="image/png")
