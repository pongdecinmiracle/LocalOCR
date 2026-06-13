"""Password hashing and signed-cookie session tokens (stdlib only).

- Passwords: PBKDF2-HMAC-SHA256 with a per-user random salt.
- Sessions: an HMAC-SHA256 signed token stored in an httpOnly cookie, so image
  <img> requests authenticate automatically without exposing the token to JS.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

from app.config import PBKDF2_ITERATIONS, SECRET_FILE, SECRET_KEY, SESSION_DAYS


def _secret() -> bytes:
    """Resolve the signing key: env var first, else a persisted random key."""
    if SECRET_KEY:
        # Accept any string; derive a fixed-length key from it.
        return hashlib.sha256(SECRET_KEY.encode()).digest()
    if SECRET_FILE.exists():
        return bytes.fromhex(SECRET_FILE.read_text().strip())
    key = os.urandom(32)
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
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


# ---------------- session tokens ----------------
# Tokens embed the user's token_version: bumping the version in the DB (on
# password change/reset) invalidates every previously issued session.
def create_token(user_id: str, token_version: int, days: int = SESSION_DAYS) -> str:
    exp = int(time.time()) + days * 86400
    payload = f"{user_id}:{token_version}:{exp}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def verify_token(token: str) -> tuple[str, int] | None:
    """Return (user_id, token_version) for a valid, unexpired token."""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id, version, exp, sig = raw.split(":")
    except Exception:
        return None
    expected = hmac.new(
        _secret(), f"{user_id}:{version}:{exp}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        if int(exp) < int(time.time()):
            return None
        return user_id, int(version)
    except ValueError:
        return None
