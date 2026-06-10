"""Rasterize uploaded documents (PDF or images) into page PNGs.

PyMuPDF (fitz) opens both PDFs and common image formats, so a single code
path handles every upload. Pages are written as PNGs and also returned as
in-memory crops on demand during extraction.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from config import PAGES, RENDER_DPI


@dataclass
class PageInfo:
    index: int
    width: int   # pixels at RENDER_DPI
    height: int
    url: str     # web path to the rendered PNG


def _zoom_for_dpi(dpi: int) -> float:
    # PyMuPDF renders at 72 DPI by default; scale up to the requested DPI.
    return dpi / 72.0


def render_document(upload_id: str, file_path: Path, dpi: int = RENDER_DPI) -> list[PageInfo]:
    """Render every page of the document to PNG under data/pages/<upload_id>/.

    Returns metadata for each page (pixel size + served URL).
    """
    out_dir = PAGES / upload_id
    out_dir.mkdir(parents=True, exist_ok=True)

    zoom = _zoom_for_dpi(dpi)
    matrix = fitz.Matrix(zoom, zoom)

    pages: list[PageInfo] = []
    doc = fitz.open(file_path)
    try:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_path = out_dir / f"page_{i}.png"
            pix.save(png_path)
            pages.append(
                PageInfo(
                    index=i,
                    width=pix.width,
                    height=pix.height,
                    url=f"/data/pages/{upload_id}/page_{i}.png",
                )
            )
    finally:
        doc.close()
    return pages


def load_page_image(upload_id: str, page_index: int) -> Image.Image:
    """Load a previously rendered page as a PIL image."""
    png_path = PAGES / upload_id / f"page_{page_index}.png"
    return Image.open(png_path).convert("RGB")


def crop_normalized(img: Image.Image, box: dict, pad: float = 0.004) -> Image.Image:
    """Crop a region given a normalized box {x,y,w,h} in 0..1 coordinates.

    A small padding is added so characters at the box edge aren't clipped.
    """
    W, H = img.size
    x = max(0.0, box["x"] - pad)
    y = max(0.0, box["y"] - pad)
    w = min(1.0 - x, box["w"] + 2 * pad)
    h = min(1.0 - y, box["h"] + 2 * pad)
    left = int(round(x * W))
    top = int(round(y * H))
    right = int(round((x + w) * W))
    bottom = int(round((y + h) * H))
    right = max(right, left + 1)
    bottom = max(bottom, top + 1)
    return img.crop((left, top, right, bottom))


def upscale_for_ocr(img: Image.Image, min_h: int = 220, min_w: int = 320, max_scale: float = 5.0) -> Image.Image:
    """Upscale a small crop so fine text is sharp enough for the vision model.

    Tight single-value crops are often only ~80-100px tall after rasterizing,
    which causes digit misreads. Scaling up with LANCZOS recovers accuracy at
    negligible cost.
    """
    w, h = img.size
    scale = max(min_h / h, min_w / w, 1.0)
    scale = min(scale, max_scale)
    if scale > 1.01:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def image_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
