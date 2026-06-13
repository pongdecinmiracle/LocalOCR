"""Central configuration for the LocalOCR backend service.

Everything is driven by environment variables so the same image runs in dev and
production. Files (uploaded originals, rendered page PNGs, Excel exports) live on
a shared volume under LOCALOCR_DATA_DIR; structured data (users, templates,
upload metadata) lives in PostgreSQL.
"""
from __future__ import annotations

import os
from pathlib import Path


def _bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


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
COOKIE_SECURE = _bool("LOCALOCR_COOKIE_SECURE")
COOKIE_NAME = "localocr_session"
SESSION_DAYS = 30
PBKDF2_ITERATIONS = 200_000

# Open self-registration. When false, only admins can create accounts (the very
# first account is always allowed so a fresh install can bootstrap its admin).
ALLOW_REGISTRATION = _bool("LOCALOCR_ALLOW_REGISTRATION", "true")

# In-app brute-force lockout for /login (per IP+username, per worker process).
# nginx adds a shared per-IP rate limit in front of this.
LOGIN_MAX_FAILURES = _int("LOCALOCR_LOGIN_MAX_FAILURES", 5)
LOGIN_LOCKOUT_SECONDS = _int("LOCALOCR_LOGIN_LOCKOUT_SECONDS", 300)

# ---- uploads / quotas ----
ALLOWED_UPLOAD_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
MAX_UPLOAD_MB = _int("LOCALOCR_MAX_UPLOAD_MB", 50)      # per file
USER_QUOTA_MB = _int("LOCALOCR_USER_QUOTA_MB", 2048)    # per user, all files
MAX_PAGES = _int("LOCALOCR_MAX_PAGES", 200)             # per document
EXPORTS_KEEP = _int("LOCALOCR_EXPORTS_KEEP", 20)        # newest xlsx kept per user

# ---- vision model (Ollama) ----
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
VISION_MODEL = os.environ.get("LOCALOCR_MODEL", "qwen2.5vl:7b")

# Context window for extraction calls. A full page image alone costs ~4k
# tokens for qwen2.5-VL, so Ollama's 4096 default rejects page + prompt with
# a 400 "exceeds the available context size". 8192 fits a page plus a large
# field list; raise it for very dense templates (costs VRAM for KV cache).
NUM_CTX = _int("LOCALOCR_NUM_CTX", 8192)

# Layers to offload to the GPU per request. 999 = "all of them", which forces
# full GPU residency instead of Ollama's conservative auto-estimate (that can
# leave some layers on the CPU). Lower it only if a model is too big for VRAM
# and you deliberately want partial CPU offload.
NUM_GPU = _int("LOCALOCR_NUM_GPU", 999)

# Extraction pipeline:
#   "vlm"      — send the page image straight to LOCALOCR_MODEL (default).
#   "thai-ocr" — two-stage: Typhoon OCR (Thai-specialised) transcribes the
#                page to markdown, then LOCALOCR_MODEL extracts the template
#                fields from that text. Far more accurate for Thai documents.
EXTRACT_MODE = os.environ.get("LOCALOCR_EXTRACT_MODE", "vlm").lower()
TYPHOON_MODEL = os.environ.get("LOCALOCR_TYPHOON_MODEL", "scb10x/typhoon-ocr1.5-3b")

# Rendering DPI used when rasterizing pages for the LLM. Higher = sharper,
# slower. 200 is a good balance for typed documents.
RENDER_DPI = int(os.environ.get("LOCALOCR_DPI", "200"))

# ---- logging ----
LOG_LEVEL = os.environ.get("LOCALOCR_LOG_LEVEL", "INFO").upper()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USERS_DIR.mkdir(parents=True, exist_ok=True)
