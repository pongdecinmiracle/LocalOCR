"""Queue extraction jobs, poll their progress, and export results to Excel."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import config, jobs
from app.config import VISION_MODEL
from app.deps import current_user, get_db
from app.excel_export import export_results
from app.models import Upload
from app.ollama_client import installed_models, model_in
from app.schemas import ExportRequest, ExtractRequest
from app.services import templates as template_svc
from app.storage import prune_exports, user_exports

router = APIRouter(prefix="/api", tags=["extraction"])


def _required_models(mode: str) -> list[str]:
    models = [VISION_MODEL]
    if mode == "thai-ocr":
        models.append(config.TYPHOON_MODEL)
    return models


@router.get("/status")
def status(user: dict = Depends(current_user)):
    names = installed_models()
    return {
        "ollama_up": names is not None,
        "model": VISION_MODEL,
        "mode": config.EXTRACT_MODE,
        "model_ready": names is not None
        and all(model_in(names, m) for m in _required_models(config.EXTRACT_MODE)),
    }


@router.post("/extract")
def extract(req: ExtractRequest, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    template = template_svc.get_template(db, user["id"], req.template_id)
    if not template:
        raise HTTPException(404, "template not found")

    names = installed_models()
    if names is None:
        raise HTTPException(503, "Ollama is not running.")
    mode = template.get("extract_mode") or config.EXTRACT_MODE
    missing = [m for m in _required_models(mode) if not model_in(names, m)]
    if missing:
        raise HTTPException(
            503,
            "Model(s) not installed yet: "
            + ", ".join(missing)
            + ". Run: "
            + " && ".join(f"ollama pull {m}" for m in missing),
        )

    # Only queue documents this user actually owns.
    owned = [
        uid
        for uid in req.upload_ids
        if (row := db.get(Upload, uid)) and row.user_id == user["id"]
    ]
    if not owned:
        raise HTTPException(400, "No valid documents selected.")

    return jobs.create_job(db, user["id"], req.template_id, owned)


@router.get("/extract/jobs/{job_id}")
def job_status(job_id: str, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    job = jobs.get_job(db, user["id"], job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.post("/export")
def export(req: ExportRequest, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    template = template_svc.get_template(db, user["id"], req.template_id)
    if not template:
        raise HTTPException(404, "template not found")
    path = export_results(template, req.results, user_exports(user["id"]))
    prune_exports(user["id"], keep=config.EXPORTS_KEEP)
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
