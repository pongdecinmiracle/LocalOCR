"""User accounts, backed by the database.

Mirrors the old auth.py behaviour exactly — same validation rules, the first
account becomes an admin, and last-admin protections — but persists to
PostgreSQL instead of users.json.
"""
from __future__ import annotations

import time

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.security import hash_password, verify_password


def _public(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "created_at": u.created_at,
        "is_admin": bool(u.is_admin),
    }


def _count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def count_users(db: Session) -> int:
    return _count(db)


def _admin_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True))) or 0


def create_user(db: Session, username: str, password: str, is_admin: bool = False) -> dict:
    """Create a user. The very first account is always an admin.

    Raises ValueError on bad input or duplicate username.
    """
    username = (username or "").strip()
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if len(password or "") < 6:
        raise ValueError("Password must be at least 6 characters.")

    key = username.lower()
    if db.scalar(select(User).where(User.username_key == key)):
        raise ValueError("That username is already taken.")

    h, salt = hash_password(password)
    user = User(
        username=username,
        username_key=key,
        password_hash=h,
        salt=salt,
        is_admin=bool(is_admin) or _count(db) == 0,
        created_at=int(time.time()),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("That username is already taken.")
    db.refresh(user)
    out = _public(user)
    out["token_version"] = user.token_version or 0
    return out


def authenticate(db: Session, username: str, password: str) -> dict | None:
    user = db.scalar(select(User).where(User.username_key == (username or "").strip().lower()))
    if not user or not verify_password(password, user.password_hash, user.salt):
        return None
    out = _public(user)
    out["token_version"] = user.token_version or 0
    return out


def get_user_by_id(db: Session, user_id: str) -> dict | None:
    user = db.get(User, user_id)
    return _public(user) if user else None


def get_auth(db: Session, user_id: str) -> dict | None:
    """Like get_user_by_id but includes token_version, for session validation."""
    user = db.get(User, user_id)
    if not user:
        return None
    out = _public(user)
    out["token_version"] = user.token_version or 0
    return out


def touch_last_seen(db: Session, user_id: str) -> None:
    db.execute(update(User).where(User.id == user_id).values(last_seen=int(time.time())))
    db.commit()


def count_active_users(db: Session, window_seconds: int = 300) -> int:
    cutoff = int(time.time()) - window_seconds
    return (
        db.scalar(select(func.count()).select_from(User).where(User.last_seen >= cutoff)) or 0
    )


# ---------------- admin management ----------------
def ensure_admin(db: Session) -> None:
    """If accounts exist but none is admin, promote the oldest one."""
    if _count(db) == 0 or _admin_count(db) > 0:
        return
    oldest = db.scalar(select(User).order_by(User.created_at.asc()))
    if oldest:
        oldest.is_admin = True
        db.commit()


def list_all_users(db: Session) -> list[dict]:
    users = db.scalars(select(User).order_by(User.created_at.asc())).all()
    return [_public(u) for u in users]


def set_admin(db: Session, user_id: str, value: bool) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found.")
    if not value and user.is_admin and _admin_count(db) <= 1:
        raise ValueError("There must be at least one admin.")
    user.is_admin = bool(value)
    db.commit()
    return _public(user)


def set_password(db: Session, user_id: str, new_password: str) -> dict:
    if len(new_password or "") < 6:
        raise ValueError("Password must be at least 6 characters.")
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found.")
    user.password_hash, user.salt = hash_password(new_password)
    # Invalidate every session issued before this password change.
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return _public(user)


def delete_user(db: Session, user_id: str) -> bool:
    user = db.get(User, user_id)
    if not user:
        return False
    if user.is_admin and _admin_count(db) <= 1:
        raise ValueError("Cannot delete the last admin.")
    db.delete(user)
    db.commit()
    return True
