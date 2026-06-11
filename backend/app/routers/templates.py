"""CRUD for per-user layout templates."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.services import templates as template_svc

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def list_templates(user: dict = Depends(current_user), db: Session = Depends(get_db)):
    return {"templates": template_svc.list_templates(db, user["id"])}


@router.get("/{template_id}")
def get_template(template_id: str, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    t = template_svc.get_template(db, user["id"], template_id)
    if not t:
        raise HTTPException(404, "template not found")
    return t


@router.post("")
def save_template(body: dict, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    if not body.get("name"):
        raise HTTPException(400, "template name is required")
    try:
        return template_svc.save_template(db, user["id"], body)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{template_id}")
def delete_template(template_id: str, user: dict = Depends(current_user), db: Session = Depends(get_db)):
    if not template_svc.delete_template(db, user["id"], template_id):
        raise HTTPException(404, "template not found")
    return {"deleted": template_id}
