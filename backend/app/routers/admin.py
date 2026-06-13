"""Admin-only user management and the performance monitor."""
from __future__ import annotations

import shutil as _shutil
import time

import psutil
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import config
from app.deps import current_admin, get_db
from app.models import ExtractionJob, Template, Upload, User
from app.ollama_client import installed_models, loaded_models, model_in
from app.schemas import AdminCreate, AdminToggle, PasswordReset
from app.services import users as user_svc

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _counts(db: Session, user_id: str) -> dict:
    templates = db.scalar(
        select(func.count()).select_from(Template).where(Template.user_id == user_id)
    )
    uploads = db.scalar(
        select(func.count()).select_from(Upload).where(Upload.user_id == user_id)
    )
    return {"templates": templates or 0, "uploads": uploads or 0}


@router.get("/metrics")
def metrics(admin: dict = Depends(current_admin), db: Session = Depends(get_db)):
    """Host/app performance snapshot for the admin Monitor page.

    CPU and memory figures are host-wide (containers share the host's
    /proc). GPU usage is reported as the model's VRAM residency from
    Ollama — the backend container itself has no GPU access.
    """
    vm = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=0.2)
    disk = _shutil.disk_usage(str(config.DATA_DIR))

    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    installed = installed_models()
    loaded = loaded_models()
    models = [
        {
            "name": m.get("name", "?"),
            "size_mb": round((m.get("size") or 0) / 1048576),
            "vram_mb": round((m.get("size_vram") or 0) / 1048576),
        }
        for m in (loaded or [])
    ]

    def _jobs(status: str) -> int:
        return (
            db.scalar(
                select(func.count())
                .select_from(ExtractionJob)
                .where(ExtractionJob.status == status)
            )
            or 0
        )

    day_ago = int(time.time()) - 86400
    failed_24h = (
        db.scalar(
            select(func.count())
            .select_from(ExtractionJob)
            .where(ExtractionJob.status == "error", ExtractionJob.updated_at >= day_ago)
        )
        or 0
    )
    recent_failures = [
        {
            "time": job.updated_at,
            "username": username,
            "documents": job.total,
            "error": job.error or "",
        }
        for job, username in db.execute(
            select(ExtractionJob, User.username)
            .join(User, User.id == ExtractionJob.user_id)
            .where(ExtractionJob.status == "error")
            .order_by(ExtractionJob.updated_at.desc())
            .limit(10)
        ).all()
    ]

    return {
        "cpu": {"percent": cpu_percent, "cores": psutil.cpu_count() or 0},
        "memory": {
            "used_mb": round(vm.used / 1048576),
            "total_mb": round(vm.total / 1048576),
            "percent": vm.percent,
        },
        "disk": {
            "used_mb": round(disk.used / 1048576),
            "total_mb": round(disk.total / 1048576),
            "percent": round(disk.used / disk.total * 100, 1) if disk.total else 0,
        },
        "gpu": {"ollama_up": loaded is not None, "loaded_models": models},
        "services": {
            "database": db_status,
            "ollama": "ok" if installed is not None else "down",
            "model": (
                ("ready" if model_in(installed) else "not installed")
                if installed is not None
                else "unknown"
            ),
        },
        "errors": {
            "jobs_done_total": _jobs("done"),
            "jobs_failed_total": _jobs("error"),
            "jobs_failed_24h": failed_24h,
            "recent_failures": recent_failures,
        },
        "activity": {
            "active_users_5m": user_svc.count_active_users(db, 300),
            "total_users": user_svc.count_users(db),
            "jobs_queued": _jobs("queued"),
            "jobs_running": _jobs("running"),
        },
    }


@router.get("/users")
def list_users(admin: dict = Depends(current_admin), db: Session = Depends(get_db)):
    users = user_svc.list_all_users(db)
    for u in users:
        u["counts"] = _counts(db, u["id"])
    return {"users": users, "me": admin["id"]}


@router.post("/users")
def create_user(body: AdminCreate, admin: dict = Depends(current_admin), db: Session = Depends(get_db)):
    try:
        user = user_svc.create_user(db, body.username, body.password, is_admin=body.is_admin)
    except ValueError as e:
        raise HTTPException(400, str(e))
    user.pop("token_version", None)
    return user


@router.post("/users/{user_id}/password")
def reset_password(
    user_id: str, body: PasswordReset, admin: dict = Depends(current_admin), db: Session = Depends(get_db)
):
    try:
        return user_svc.set_password(db, user_id, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/users/{user_id}/admin")
def set_admin(
    user_id: str, body: AdminToggle, admin: dict = Depends(current_admin), db: Session = Depends(get_db)
):
    try:
        return user_svc.set_admin(db, user_id, body.is_admin)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/users/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(current_admin), db: Session = Depends(get_db)):
    if user_id == admin["id"]:
        raise HTTPException(400, "You cannot delete your own account here.")
    try:
        ok = user_svc.delete_user(db, user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "user not found")
    # Remove all of that user's files. DB rows (templates, uploads) cascade.
    from app.storage import delete_user_files

    delete_user_files(user_id)
    return {"deleted": user_id}
