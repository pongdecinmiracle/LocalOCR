"""Central configuration and on-disk paths for LocalOCR.

Storage is per-user: everything a user owns lives under
data/users/<user_id>/{templates,uploads,pages,exports}/.
"""
import os
from pathlib import Path

# Root of the project (parent of this backend/ folder)
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
USERS_DIR = DATA / "users"          # per-user data lives here
USERS_FILE = DATA / "users.json"    # account records
SECRET_FILE = DATA / "secret.key"   # HMAC key for session tokens

for _p in (DATA, USERS_DIR):
    _p.mkdir(parents=True, exist_ok=True)


# ---- per-user path helpers ----
def user_root(user_id: str) -> Path:
    return USERS_DIR / user_id


def user_templates(user_id: str) -> Path:
    p = user_root(user_id) / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_uploads(user_id: str) -> Path:
    p = user_root(user_id) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_pages(user_id: str) -> Path:
    p = user_root(user_id) / "pages"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_exports(user_id: str) -> Path:
    p = user_root(user_id) / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


# Ollama
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
VISION_MODEL = os.environ.get("LOCALOCR_MODEL", "qwen2.5vl:7b")

# Rendering DPI used when rasterizing pages for the LLM. Higher = sharper crops,
# slower. 200 is a good balance for typed documents.
RENDER_DPI = int(os.environ.get("LOCALOCR_DPI", "200"))
