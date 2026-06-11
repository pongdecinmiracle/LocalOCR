"""Thin client around the Ollama chat API for vision extraction."""
from __future__ import annotations

import base64

import httpx

from app.config import OLLAMA_HOST, VISION_MODEL


class OllamaError(RuntimeError):
    pass


def is_up() -> bool:
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def installed_models() -> list[str]:
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=5.0)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def model_ready(model: str = VISION_MODEL) -> bool:
    names = installed_models()
    # Ollama tags may carry a :latest suffix; match on the base name too.
    base = model.split(":")[0]
    return any(n == model or n.split(":")[0] == base for n in names)


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
        "options": {"temperature": 0},
    }
    if as_json:
        payload["format"] = "json"

    try:
        r = httpx.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise OllamaError(f"Ollama request failed: {e}") from e

    data = r.json()
    return (data.get("message") or {}).get("content", "").strip()
