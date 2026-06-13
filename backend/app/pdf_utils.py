"""Rasterize uploaded documents (PDF or images) into page PNGs.

PyMuPDF (fitz) opens both PDFs and common image formats, so a single code
path handles every upload. Pages are written as PNGs and also returned as
in-memory crops on demand during extraction.
"""
from __future__ import annotations

import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image

from app.config import RENDER_DPI


def _zoom_for_dpi(dpi: int) -> float:
    # PyMuPDF renders at 72 DPI by default; scale up to the requested DPI.
    return dpi / 72.0


def render_document(
    file_path: Path, out_dir: Path, dpi: int = RENDER_DPI, max_pages: int | None = None
) -> list[dict]:
    """Render every page of the document to page_<i>.png under out_dir.

    Returns metadata for each page: {index, width, height} in pixels.
    Raises ValueError if the document exceeds max_pages.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    zoom = _zoom_for_dpi(dpi)
    matrix = fitz.Matrix(zoom, zoom)

    pages: list[dict] = []
    doc = fitz.open(file_path)
    try:
        if max_pages is not None and doc.page_count > max_pages:
            raise ValueError(
                f"document has {doc.page_count} pages (limit is {max_pages})"
            )
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pix.save(out_dir / f"page_{i}.png")
            # Save the page's text layer (empty for scans/images): Typhoon OCR
            # uses it as anchor text to improve transcription accuracy.
            try:
                (out_dir / f"page_{i}.txt").write_text(
                    page.get_text()[:4000], encoding="utf-8"
                )
            except Exception:
                pass
            pages.append({"index": i, "width": pix.width, "height": pix.height})
    finally:
        doc.close()
    return pages


def load_page_image(pages_dir: Path, page_index: int) -> Image.Image:
    """Load a previously rendered page (pages_dir/page_<i>.png) as a PIL image."""
    return Image.open(pages_dir / f"page_{page_index}.png").convert("RGB")


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
