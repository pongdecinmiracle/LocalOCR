"""Central configuration and on-disk paths for LocalOCR."""
import os
from pathlib import Path

# Root of the project (parent of this backend/ folder)
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

UPLOADS = DATA / "uploads"      # original uploaded files
PAGES = DATA / "pages"          # rendered page images (png), per upload
TEMPLATES = DATA / "templates"  # template definitions (json)
EXPORTS = DATA / "exports"      # generated .xlsx files

for _p in (UPLOADS, PAGES, TEMPLATES, EXPORTS):
    _p.mkdir(parents=True, exist_ok=True)

# Ollama
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
VISION_MODEL = os.environ.get("LOCALOCR_MODEL", "qwen2.5vl:7b")

# Rendering DPI used when rasterizing pages for the LLM. Higher = sharper crops,
# slower. 200 is a good balance for typed documents.
RENDER_DPI = int(os.environ.get("LOCALOCR_DPI", "200"))
