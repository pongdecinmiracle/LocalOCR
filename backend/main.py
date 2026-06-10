"""LocalOCR FastAPI application: upload, template editing, extraction, export."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import templates_store
from config import DATA, EXPORTS, PAGES, UPLOADS, VISION_MODEL
from excel_export import export_results
from extract import extract_document
from ollama_client import OllamaError, is_up, model_ready
from pdf_utils import render_document

app = FastAPI(title="LocalOCR")

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

# Serve rendered pages and generated exports.
app.mount("/data", StaticFiles(directory=DATA), name="data")


# ---------- models ----------
class ExtractRequest(BaseModel):
    template_id: str
    upload_ids: list[str]


class ExportRequest(BaseModel):
    template_id: str
    results: list[dict]


# ---------- status ----------
@app.get("/api/status")
def status():
    return {
        "ollama_up": is_up(),
        "model": VISION_MODEL,
        "model_ready": model_ready(),
    }


# ---------- uploads ----------
def _upload_meta_path(upload_id: str) -> Path:
    return UPLOADS / upload_id / "meta.json"


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)):
    out = []
    for f in files:
        upload_id = uuid.uuid4().hex[:12]
        dest_dir = UPLOADS / upload_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f.filename
        with dest.open("wb") as buf:
            shutil.copyfileobj(f.file, buf)

        try:
            pages = render_document(upload_id, dest)
        except Exception as e:
            raise HTTPException(400, f"Could not read '{f.filename}': {e}")

        meta = {
            "upload_id": upload_id,
            "filename": f.filename,
            "pages": [p.__dict__ for p in pages],
        }
        _upload_meta_path(upload_id).write_text(json.dumps(meta), encoding="utf-8")
        out.append(meta)
    return {"uploads": out}


@app.get("/api/upload/{upload_id}")
def get_upload(upload_id: str):
    p = _upload_meta_path(upload_id)
    if not p.exists():
        raise HTTPException(404, "upload not found")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- templates ----------
@app.get("/api/templates")
def list_templates():
    return {"templates": templates_store.list_templates()}


@app.get("/api/templates/{template_id}")
def get_template(template_id: str):
    t = templates_store.get_template(template_id)
    if not t:
        raise HTTPException(404, "template not found")
    return t


@app.post("/api/templates")
def save_template(body: dict):
    if not body.get("name"):
        raise HTTPException(400, "template name is required")
    return templates_store.save_template(body)


@app.delete("/api/templates/{template_id}")
def delete_template(template_id: str):
    ok = templates_store.delete_template(template_id)
    if not ok:
        raise HTTPException(404, "template not found")
    return {"deleted": template_id}


# ---------- extraction ----------
@app.post("/api/extract")
def extract(req: ExtractRequest):
    template = templates_store.get_template(req.template_id)
    if not template:
        raise HTTPException(404, "template not found")
    if not is_up():
        raise HTTPException(503, "Ollama is not running. Start it with 'ollama serve'.")
    if not model_ready():
        raise HTTPException(
            503, f"Model '{VISION_MODEL}' is not installed yet. Run: ollama pull {VISION_MODEL}"
        )

    results = []
    for uid in req.upload_ids:
        meta_path = _upload_meta_path(uid)
        filename = uid
        if meta_path.exists():
            filename = json.loads(meta_path.read_text(encoding="utf-8")).get("filename", uid)
        try:
            res = extract_document(uid, template, VISION_MODEL)
        except OllamaError as e:
            raise HTTPException(502, str(e))
        results.append({"upload_id": uid, "file": filename, "fields": res["fields"]})
    return {"results": results}


# ---------- export ----------
@app.post("/api/export")
def export(req: ExportRequest):
    template = templates_store.get_template(req.template_id)
    if not template:
        raise HTTPException(404, "template not found")
    path = export_results(template, req.results)
    fname = Path(path).name
    return {"url": f"/data/exports/{fname}", "filename": fname}


@app.get("/api/download/{fname}")
def download(fname: str):
    path = EXPORTS / fname
    if not path.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=fname,
    )


# ---------- frontend ----------
@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
