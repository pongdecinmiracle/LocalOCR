"""Registration, login, logout and the current-user endpoint."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import config
from app.deps import client_ip, current_user, get_db, set_session_cookie
from app.ratelimit import login_limiter
from app.schemas import Credentials
from app.services import users as user_svc

log = logging.getLogger("localocr.auth")

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/auth-config")
def auth_config(db: Session = Depends(get_db)):
    """Public: tells the login screen whether self-registration is open."""
    bootstrap = user_svc.count_users(db) == 0
    return {"allow_registration": config.ALLOW_REGISTRATION or bootstrap}


@router.post("/register")
def register(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
):
    # The very first account may always be created (bootstrap admin); after
    # that, self-registration can be disabled for invite-only deployments.
    if not config.ALLOW_REGISTRATION and user_svc.count_users(db) > 0:
        raise HTTPException(403, "Self-registration is disabled. Ask an admin for an account.")
    try:
        user = user_svc.create_user(db, body.username, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    set_session_cookie(response, user["id"], user.pop("token_version"))
    log.info("user registered: %s (id=%s, ip=%s)", user["username"], user["id"], client_ip(request))
    return user


@router.post("/login")
def login(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
):
    key = f"{client_ip(request)}:{(body.username or '').strip().lower()}"
    wait = login_limiter.retry_after(key)
    if wait:
        log.warning("login locked out: %s", key)
        raise HTTPException(429, f"Too many failed attempts. Try again in {wait} seconds.")

    user = user_svc.authenticate(db, body.username, body.password)
    if not user:
        login_limiter.record_failure(key)
        log.warning("login failed: user=%s ip=%s", body.username, client_ip(request))
        raise HTTPException(401, "Invalid username or password.")

    login_limiter.clear(key)
    set_session_cookie(response, user["id"], user.pop("token_version"))
    log.info("login ok: %s (id=%s, ip=%s)", user["username"], user["id"], client_ip(request))
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(config.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
