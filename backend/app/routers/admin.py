"""Admin-only user management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import current_admin, get_db
from app.models import Template, Upload
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


@router.get("/users")
def list_users(admin: dict = Depends(current_admin), db: Session = Depends(get_db)):
    users = user_svc.list_all_users(db)
    for u in users:
        u["counts"] = _counts(db, u["id"])
    return {"users": users, "me": admin["id"]}


@router.post("/users")
def create_user(body: AdminCreate, admin: dict = Depends(current_admin), db: Session = Depends(get_db)):
    try:
        return user_svc.create_user(db, body.username, body.password, is_admin=body.is_admin)
    except ValueError as e:
        raise HTTPException(400, str(e))


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
