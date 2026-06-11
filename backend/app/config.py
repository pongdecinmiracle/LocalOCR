"""Central configuration for the LocalOCR backend service.

Everything is driven by environment variables so the same image runs in dev and
production. Files (uploaded originals, rendered page PNGs, Excel exports) live on
a shared volume under LOCALOCR_DATA_DIR; structured data (users, templates,
upload metadata) lives in PostgreSQL.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---- storage (shared volume) ----
DATA_DIR = Path(os.environ.get("LOCALOCR_DATA_DIR", "/data"))
USERS_DIR = DATA_DIR / "users"          # per-user files live here
SECRET_FILE = DATA_DIR / "secret.key"   # fallback HMAC key if no env secret

# ---- database ----
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://localocr:localocr@db:5432/localocr",
)

# ---- security ----
# If set, this signs session cookies. Otherwise a key is generated and persisted
# to SECRET_FILE on the data volume (fine for single-node, less so for scale-out).
SECRET_KEY = os.environ.get("LOCALOCR_SECRET_KEY") or ""
COOKIE_SECURE = os.environ.get("LOCALOCR_COOKIE_SECURE", "false").lower() == "true"
COOKIE_NAME = "localocr_session"
SESSION_DAYS = 30
PBKDF2_ITERATIONS = 200_000

# ---- vision model (Ollama) ----
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
VISION_MODEL = os.environ.get("LOCALOCR_MODEL", "qwen2.5vl:7b")

# Rendering DPI used when rasterizing pages for the LLM. Higher = sharper,
# slower. 200 is a good balance for typed documents.
RENDER_DPI = int(os.environ.get("LOCALOCR_DPI", "200"))


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USERS_DIR.mkdir(parents=True, exist_ok=True)
