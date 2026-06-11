"""Run extraction over uploaded documents and export results to Excel."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import VISION_MODEL
from app.deps import current_user, get_db
from app.excel_export import export_results
from app.extract import extract_document
from app.models import Upload
from app.ollama_client import OllamaError, is_up, model_ready
from app.schemas import ExportRequest, ExtractRequest
from app.services import templates as template_svc
from app.storage import user_exports, user_pages

router = APIRouter(prefix="/api", tags=["extraction"])


@router.get("/status")
def status(user: dict = Depends(current_user)):
    return {"ollama_up": is_up(), "model": VISION_MODEL, "model_ready": model_ready()}


@router.post("/extract")
def extract(req: ExtractRequest, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    template = template_svc.get_template(db, user["id"], req.template_id)
    if not template:
        raise HTTPException(404, "template not found")
    if not is_up():
        raise HTTPException(503, "Ollama is not running.")
    if not model_ready():
        raise HTTPException(
            503, f"Model '{VISION_MODEL}' is not installed yet. Run: ollama pull {VISION_MODEL}"
        )

    results = []
    for uid in req.upload_ids:
        row = db.get(Upload, uid)
        if not row or row.user_id != user["id"]:
            continue
        pages_dir = user_pages(user["id"]) / uid
        try:
            res = extract_document(pages_dir, template, VISION_MODEL)
        except OllamaError as e:
            raise HTTPException(502, str(e))
        results.append({"upload_id": uid, "file": row.filename, "fields": res["fields"]})
    return {"results": results}


@router.post("/export")
def export(req: ExportRequest, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    template = template_svc.get_template(db, user["id"], req.template_id)
    if not template:
        raise HTTPException(404, "template not found")
    path = export_results(template, req.results, user_exports(user["id"]))
    return {"url": f"/api/download/{Path(path).name}", "filename": Path(path).name}


@router.get("/download/{fname}")
def download(fname: str, user: dict = Depends(current_user)):
    # Guard against path traversal; only serve a flat filename.
    path = user_exports(user["id"]) / Path(fname).name
    if not path.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )
