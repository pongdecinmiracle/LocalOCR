"""Thin client around the Ollama chat API for vision extraction and Thai OCR."""
from __future__ import annotations

import base64
import json

import httpx

from app.config import NUM_CTX, NUM_GPU, OLLAMA_HOST, TYPHOON_MODEL, VISION_MODEL


class OllamaError(RuntimeError):
    pass


# Typhoon OCR models only work with their fixed training prompt (see the
# scb10x model card); the anchor slot takes the PDF's own text layer as a hint.
TYPHOON_OCR_PROMPT = (
    "Below is an image of a document page along with its dimensions. "
    "Simply return the markdown representation of this document, presenting "
    "tables in markdown format as they naturally appear.\n"
    "If the document contains images, use a placeholder like dummy.png for each image.\n"
    "Your final output must be in JSON format with a single key `natural_text` "
    "containing the response.\n"
    "RAW_TEXT_START\n{anchor}\nRAW_TEXT_END"
)


def installed_models() -> list[str] | None:
    """List of installed model tags, or None when Ollama is unreachable."""
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return None


def is_up() -> bool:
    return installed_models() is not None


def loaded_models() -> list[dict] | None:
    """Models currently loaded into (V)RAM, or None when Ollama is unreachable.

    Each entry includes name, size (total bytes in memory) and size_vram
    (bytes of that residing in GPU memory).
    """
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/ps", timeout=5.0)
        r.raise_for_status()
        return r.json().get("models", [])
    except Exception:
        return None


def model_in(names: list[str] | None, model: str = VISION_MODEL) -> bool:
    # Ollama tags may carry a :latest suffix; match on the base name too.
    base = model.split(":")[0]
    return any(n == model or n.split(":")[0] == base for n in names or [])


def model_ready(model: str = VISION_MODEL) -> bool:
    return model_in(installed_models(), model)


def _chat(payload: dict, timeout: float) -> str:
    try:
        r = httpx.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        # Surface Ollama's own error message (e.g. "exceeds the available
        # context size") instead of a bare HTTP status.
        detail = ""
        try:
            detail = (e.response.json().get("error") or e.response.text or "").strip()
        except Exception:
            detail = (e.response.text or "").strip()
        raise OllamaError(
            f"Ollama rejected the request ({e.response.status_code}): {detail[:300]}"
        ) from e
    except httpx.HTTPError as e:
        raise OllamaError(f"Ollama request failed: {e}") from e

    data = r.json()
    return (data.get("message") or {}).get("content", "").strip()


def vision_extract(
    image_png: bytes,
    prompt: str,
    *,
    model: str = VISION_MODEL,
    as_json: bool = False,
    timeout: float = 180.0,
) -> str:
    """Send one image + prompt to the vision model, return the text response."""
    b64 = base64.b64encode(image_png).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64],
            }
        ],
        "stream": False,
        # num_ctx: page image (~4k tokens) + prompt must fit; Ollama's 4096
        # default 400s on any real page + field list.
        # num_gpu: force all layers onto the GPU (no CPU offload).
        "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_gpu": NUM_GPU},
    }
    if as_json:
        payload["format"] = "json"
    return _chat(payload, timeout)


def ocr_page(
    image_png: bytes,
    anchor_text: str = "",
    *,
    model: str = TYPHOON_MODEL,
    timeout: float = 300.0,
) -> str:
    """Transcribe a page image to markdown text with Typhoon OCR (Thai/English).

    Returns the page's text; tables come back as markdown tables.
    """
    b64 = base64.b64encode(image_png).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": TYPHOON_OCR_PROMPT.format(anchor=anchor_text),
                "images": [b64],
            }
        ],
        "stream": False,
        # Generation settings from the Typhoon OCR model card (0 or 0.1 —
        # use 0 so transcriptions are deterministic run to run).
        "options": {
            "temperature": 0,
            "top_p": 0.6,
            "repeat_penalty": 1.2,
            "num_ctx": NUM_CTX,
            "num_gpu": NUM_GPU,
        },
    }
    content = _chat(payload, timeout)
    try:
        return json.loads(content).get("natural_text") or content
    except Exception:
        return content


def text_extract(
    prompt: str,
    *,
    model: str = VISION_MODEL,
    as_json: bool = False,
    timeout: float = 180.0,
) -> str:
    """Text-only chat (no image) — used to pull fields out of OCR text."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_gpu": NUM_GPU},
    }
    if as_json:
        payload["format"] = "json"
    return _chat(payload, timeout)
