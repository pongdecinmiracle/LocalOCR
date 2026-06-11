"""Registration, login, logout and the current-user endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.deps import current_user, get_db, set_session_cookie
from app.schemas import Credentials
from app.services import users as user_svc

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/register")
def register(body: Credentials, response: Response, db: Session = Depends(get_db)):
    try:
        user = user_svc.create_user(db, body.username, body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    set_session_cookie(response, user["id"])
    return user


@router.post("/login")
def login(body: Credentials, response: Response, db: Session = Depends(get_db)):
    user = user_svc.authenticate(db, body.username, body.password)
    if not user:
        raise HTTPException(401, "Invalid username or password.")
    set_session_cookie(response, user["id"])
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("localocr_session", path="/")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
