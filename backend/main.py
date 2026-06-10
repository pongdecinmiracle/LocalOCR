"""LocalOCR FastAPI app: accounts, per-user uploads, templates, extraction, export."""
from __future__ import annotations

import json
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import auth
import templates_store
from auth import COOKIE_NAME, SESSION_DAYS
from config import (
    VISION_MODEL,
    user_exports,
    user_pages,
    user_root,
    user_templates,
    user_uploads,
)
from excel_export import export_results
from extract import extract_document
from ollama_client import OllamaError, is_up, model_ready
from pdf_utils import render_document

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Make sure existing installs always have at least one admin.
    auth.ensure_admin()
    yield


app = FastAPI(title="LocalOCR", lifespan=lifespan)
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


# ---------------- models ----------------
class Credentials(BaseModel):
    username: str
    password: str


class ExtractRequest(BaseModel):
    template_id: str
    upload_ids: list[str]


class ExportRequest(BaseModel):
    template_id: str
    results: list[dict]


# ---------------- auth ----------------
def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    user_id = auth.verify_token(token) if token else None
    user = auth.get_user_by_id(user_id) if user_id else None
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def _set_session(response: Response, user_id: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        auth.create_token(user_id),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        path="/",
    )


@app.post("/api/register")
def register(body: Credentials, response: Response):
    try:
        user = auth.create_user(body.username, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _set_session(response, user["id"])
    return user


@app.post("/api/login")
def login(body: Credentials, response: Response):
    user = auth.authenticate(body.username, body.password)
    if not user:
        raise HTTPException(401, "Invalid username or password.")
    _set_session(response, user["id"])
    return user


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


# ---------------- admin ----------------
def current_admin(user: dict = Depends(current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin access required.")
    return user


class AdminCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class PasswordReset(BaseModel):
    password: str


class AdminToggle(BaseModel):
    is_admin: bool


def _user_counts(user_id: str) -> dict:
    templates = len(list(user_templates(user_id).glob("*.json")))
    up_dir = user_uploads(user_id)
    uploads = sum(1 for d in up_dir.iterdir() if (d / "meta.json").exists()) if up_dir.exists() else 0
    return {"templates": templates, "uploads": uploads}


@app.get("/api/admin/users")
def admin_list_users(admin: dict = Depends(current_admin)):
    users = auth.list_all_users()
    for u in users:
        u["counts"] = _user_counts(u["id"])
    return {"users": users, "me": admin["id"]}


@app.post("/api/admin/users")
def admin_create_user(body: AdminCreate, admin: dict = Depends(current_admin)):
    try:
        return auth.create_user(body.username, body.password, is_admin=body.is_admin)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{user_id}/password")
def admin_reset_password(user_id: str, body: PasswordReset, admin: dict = Depends(current_admin)):
    try:
        return auth.set_password(user_id, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/admin/users/{user_id}/admin")
def admin_set_admin(user_id: str, body: AdminToggle, admin: dict = Depends(current_admin)):
    try:
        return auth.set_admin(user_id, body.is_admin)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: str, admin: dict = Depends(current_admin)):
    if user_id == admin["id"]:
        raise HTTPException(400, "You cannot delete your own account here.")
    try:
        ok = auth.delete_user(user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "user not found")
    # Remove all of that user's data.
    shutil.rmtree(user_root(user_id), ignore_errors=True)
    return {"deleted": user_id}


# ---------------- status ----------------
@app.get("/api/status")
def status(user: dict = Depends(current_user)):
    return {"ollama_up": is_up(), "model": VISION_MODEL, "model_ready": model_ready()}


# ---------------- uploads ----------------
def _meta_path(user: dict, upload_id: str) -> Path:
    return user_uploads(user["id"]) / upload_id / "meta.json"


@app.post("/api/upload")
async def upload(user: dict = Depends(current_user), files: list[UploadFile] = File(...)):
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
            raise HTTPException(400, f"Could not read '{f.filename}': {e}")

        for p in pages:
            p["url"] = f"/api/page/{upload_id}/{p['index']}"
        meta = {"upload_id": upload_id, "filename": f.filename, "pages": pages}
        (dest_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        out.append(meta)
    return {"uploads": out}


@app.get("/api/uploads")
def list_uploads(user: dict = Depends(current_user)):
    out = []
    base = user_uploads(user["id"])
    if base.exists():
        for d in base.iterdir():
            meta = d / "meta.json"
            if meta.exists():
                try:
                    out.append(json.loads(meta.read_text(encoding="utf-8")))
                except Exception:
                    continue
    return {"uploads": out}


@app.delete("/api/uploads/{upload_id}")
def delete_upload(upload_id: str, user: dict = Depends(current_user)):
    up = user_uploads(user["id"]) / upload_id
    pg = user_pages(user["id"]) / upload_id
    shutil.rmtree(up, ignore_errors=True)
    shutil.rmtree(pg, ignore_errors=True)
    return {"deleted": upload_id}


@app.get("/api/page/{upload_id}/{page_index}")
def page_image(upload_id: str, page_index: int, user: dict = Depends(current_user)):
    png = user_pages(user["id"]) / upload_id / f"page_{page_index}.png"
    if not png.exists():
        raise HTTPException(404, "page not found")
    return FileResponse(png, media_type="image/png")


# ---------------- templates ----------------
@app.get("/api/templates")
def list_templates(user: dict = Depends(current_user)):
    return {"templates": templates_store.list_templates(user["id"])}


@app.get("/api/templates/{template_id}")
def get_template(template_id: str, user: dict = Depends(current_user)):
    t = templates_store.get_template(user["id"], template_id)
    if not t:
        raise HTTPException(404, "template not found")
    return t


@app.post("/api/templates")
def save_template(body: dict, user: dict = Depends(current_user)):
    if not body.get("name"):
        raise HTTPException(400, "template name is required")
    return templates_store.save_template(user["id"], body)


@app.delete("/api/templates/{template_id}")
def delete_template(template_id: str, user: dict = Depends(current_user)):
    if not templates_store.delete_template(user["id"], template_id):
        raise HTTPException(404, "template not found")
    return {"deleted": template_id}


# ---------------- extraction ----------------
@app.post("/api/extract")
def extract(req: ExtractRequest, user: dict = Depends(current_user)):
    template = templates_store.get_template(user["id"], req.template_id)
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
        meta_path = _meta_path(user, uid)
        filename = uid
        if meta_path.exists():
            filename = json.loads(meta_path.read_text(encoding="utf-8")).get("filename", uid)
        pages_dir = user_pages(user["id"]) / uid
        try:
            res = extract_document(pages_dir, template, VISION_MODEL)
        except OllamaError as e:
            raise HTTPException(502, str(e))
        results.append({"upload_id": uid, "file": filename, "fields": res["fields"]})
    return {"results": results}


# ---------------- export ----------------
@app.post("/api/export")
def export(req: ExportRequest, user: dict = Depends(current_user)):
    template = templates_store.get_template(user["id"], req.template_id)
    if not template:
        raise HTTPException(404, "template not found")
    path = export_results(template, req.results, user_exports(user["id"]))
    return {"url": f"/api/download/{Path(path).name}", "filename": Path(path).name}


@app.get("/api/download/{fname}")
def download(fname: str, user: dict = Depends(current_user)):
    path = user_exports(user["id"]) / fname
    if not path.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=fname,
    )


# ---------------- frontend ----------------
@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
