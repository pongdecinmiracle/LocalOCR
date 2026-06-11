"""Shared FastAPI dependencies: DB session and the current user/admin."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import security
from app.config import COOKIE_NAME, COOKIE_SECURE, SESSION_DAYS
from app.database import SessionLocal
from app.services import users as user_svc


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    user_id = security.verify_token(token) if token else None
    user = user_svc.get_user_by_id(db, user_id) if user_id else None
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def current_admin(user: dict = Depends(current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin access required.")
    return user


def set_session_cookie(response, user_id: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        security.create_token(user_id),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
