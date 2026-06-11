"""Upload documents, list/delete them, and serve rendered page images."""
from __future__ import annotations

import shutil
import time
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.models import Upload
from app.pdf_utils import render_document
from app.storage import delete_upload_files, user_pages, user_uploads

router = APIRouter(prefix="/api", tags=["uploads"])


@router.post("/upload")
async def upload(
    user: dict = Depends(current_user),
    db: Session = Depends(get_db),
    files: list[UploadFile] = File(...),
):
    out = []
    for f in files:
        upload_id = uuid.uuid4().hex[:12]
        dest_dir = user_uploads(user["id"]) / upload_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f.filename
        with dest.open("wb") as buf:
            shutil.copyfileobj(f.file, buf)

        pages_dir = user_pages(user["id"]) / upload_id
        try:
            pages = render_document(dest, pages_dir)
        except Exception as e:
            shutil.rmtree(dest_dir, ignore_errors=True)
            shutil.rmtree(pages_dir, ignore_errors=True)
            raise HTTPException(400, f"Could not read '{f.filename}': {e}")

        for p in pages:
            p["url"] = f"/api/page/{upload_id}/{p['index']}"

        db.add(
            Upload(
                id=upload_id,
                user_id=user["id"],
                filename=f.filename,
                pages=pages,
                created_at=int(time.time()),
            )
        )
        db.commit()
        out.append({"upload_id": upload_id, "filename": f.filename, "pages": pages})
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
