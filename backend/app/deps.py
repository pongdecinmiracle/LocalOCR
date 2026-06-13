"""Shared FastAPI dependencies: DB session and the current user/admin."""
from __future__ import annotations

import time
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import security
from app.config import COOKIE_NAME, COOKIE_SECURE, SESSION_DAYS
from app.database import SessionLocal
from app.services import users as user_svc

# Throttle last_seen writes to once a minute per user (per worker process) so
# activity tracking doesn't add a DB write to every request.
_LAST_SEEN_WRITTEN: dict[str, float] = {}
_LAST_SEEN_INTERVAL = 60.0


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    parsed = security.verify_token(token) if token else None
    user = user_svc.get_auth(db, parsed[0]) if parsed else None
    # A stale token_version means the password changed since this session was
    # issued — treat it as logged out.
    if not user or user.pop("token_version") != parsed[1]:
        raise HTTPException(401, "Not authenticated")

    now = time.time()
    if now - _LAST_SEEN_WRITTEN.get(user["id"], 0) >= _LAST_SEEN_INTERVAL:
        _LAST_SEEN_WRITTEN[user["id"]] = now
        user_svc.touch_last_seen(db, user["id"])
    return user


def current_admin(user: dict = Depends(current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Admin access required.")
    return user


def client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers behind nginx, so request.client already
    # reflects X-Forwarded-For; fall back gracefully for direct dev runs.
    return request.client.host if request.client else "unknown"


def set_session_cookie(response, user_id: str, token_version: int) -> None:
    response.set_cookie(
        COOKIE_NAME,
        security.create_token(user_id, token_version),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
