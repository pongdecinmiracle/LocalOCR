"""User accounts + signed-cookie sessions, using only the Python stdlib.

- Passwords are hashed with PBKDF2-HMAC-SHA256 and a per-user random salt.
- Sessions are a signed token (HMAC-SHA256) stored in an httpOnly cookie, so
  image <img> requests authenticate automatically without exposing the token
  to JavaScript.
- Users live in data/users.json keyed by lowercased username.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
import uuid

from config import SECRET_FILE, USERS_FILE

PBKDF2_ITERATIONS = 200_000
SESSION_DAYS = 30
COOKIE_NAME = "localocr_session"

_lock = threading.Lock()


# ---------------- secret ----------------
def _secret() -> bytes:
    if SECRET_FILE.exists():
        return bytes.fromhex(SECRET_FILE.read_text().strip())
    key = os.urandom(32)
    SECRET_FILE.write_text(key.hex())
    return key


# ---------------- password hashing ----------------
def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return dk.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(dk.hex(), hash_hex)


# ---------------- user store ----------------
def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_users(users: dict) -> None:
    USERS_FILE.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")


def create_user(username: str, password: str) -> dict:
    """Create a new user. Raises ValueError on bad input or duplicate."""
    username = (username or "").strip()
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if len(password or "") < 6:
        raise ValueError("Password must be at least 6 characters.")
    key = username.lower()
    with _lock:
        users = _load_users()
        if key in users:
            raise ValueError("That username is already taken.")
        h, salt = hash_password(password)
        user = {
            "id": uuid.uuid4().hex[:12],
            "username": username,
            "password_hash": h,
            "salt": salt,
            "created_at": int(time.time()),
        }
        users[key] = user
        _save_users(users)
    return _public(user)


def authenticate(username: str, password: str) -> dict | None:
    user = _load_users().get((username or "").strip().lower())
    if not user:
        return None
    if not verify_password(password, user["password_hash"], user["salt"]):
        return None
    return _public(user)


def get_user_by_id(user_id: str) -> dict | None:
    for user in _load_users().values():
        if user["id"] == user_id:
            return _public(user)
    return None


def _public(user: dict) -> dict:
    return {"id": user["id"], "username": user["username"], "created_at": user["created_at"]}


# ---------------- session tokens ----------------
def create_token(user_id: str, days: int = SESSION_DAYS) -> str:
    exp = int(time.time()) + days * 86400
    payload = f"{user_id}:{exp}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def verify_token(token: str) -> str | None:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, exp, sig = raw.split(":")
    except Exception:
        return None
    expected = hmac.new(_secret(), f"{user_id}:{exp}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    if int(exp) < int(time.time()):
        return None
    return user_id
