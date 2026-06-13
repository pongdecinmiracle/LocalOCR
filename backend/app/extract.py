"""Run a template's fields against a rendered document and collect values.

Design note: Qwen2.5-VL (and most VLMs) read a *full page* far more
accurately than a tight single-field crop — small crops get too few visual
tokens and digits get misread. So extraction sends the whole page once and
asks for every field on that page as structured JSON. The template's boxes
still drive everything: they define which fields exist, their types/columns,
and a location hint (top-right, bottom-center, …) that disambiguates
similar-looking fields.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app import config
from app.ollama_client import ocr_page, text_extract, vision_extract
from app.pdf_utils import image_to_png_bytes, load_page_image

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _coerce_number(value):
    if value is None or isinstance(value, (int, float)):
        return value
    m = _NUM_RE.search(str(value).replace(" ", ""))
    if not m:
        return value
    raw = m.group(0).replace(",", "")
    try:
        f = float(raw)
        return int(f) if f.is_integer() else f
    except ValueError:
        return value


def _location_hint(box: dict) -> str:
    cx = box["x"] + box["w"] / 2
    cy = box["y"] + box["h"] / 2
    vert = "top" if cy < 0.34 else "middle" if cy < 0.67 else "bottom"
    horiz = "left" if cx < 0.34 else "center" if cx < 0.67 else "right"
    return f"{vert}-{horiz}"


def _field_line(field: dict) -> str:
    loc = _location_hint(field["box"])
    if field["type"] == "table":
        cols = ", ".join(
            f'"{c["name"]}" ({c.get("type", "text")})' for c in field.get("columns", [])
        )
        return (
            f'- "{field["name"]}" (table) — the "{field["label"]}" table located in the '
            f"{loc} area of the page. Return an array of row objects, one per data row "
            f"(exclude the header row), each with columns: {cols}."
        )
    type_hint = {
        "number": "a number — digits only",
        "date": "a date, kept exactly as written",
        "text": "text",
    }.get(field["type"], "text")
    return (
        f'- "{field["name"]}" ({field["type"]}) — {type_hint}; this is the '
        f'"{field["label"]}" value located in the {loc} area of the page.'
    )


def _build_prompt(fields: list[dict]) -> str:
    field_lines = "\n".join(_field_line(f) for f in fields)
    keys = [f["name"] for f in fields]
    return (
        "You are a precise document data extractor. Read the document image and "
        "extract the following fields. Use the location hints to find each field, "
        "but rely on the visible labels and values to read the exact text.\n\n"
        f"Fields:\n{field_lines}\n\n"
        f"Return ONLY a JSON object with exactly these keys: {keys}. "
        "For a table field the value is an array of row objects. "
        "Use null for any field that is not present. Read values exactly as "
        "printed — do not guess, round, or invent digits."
    )


def _build_text_prompt(fields: list[dict], doc_text: str) -> str:
    """Prompt for stage two of thai-ocr mode: fields from transcribed text."""
    field_lines = "\n".join(_field_line(f) for f in fields)
    keys = [f["name"] for f in fields]
    return (
        "You are a precise document data extractor. Below is the OCR transcription "
        "of a document page (tables appear as markdown tables). Extract the "
        "following fields from it. The location hints describe where each field "
        "sat on the original page.\n\n"
        f"Fields:\n{field_lines}\n\n"
        f"Document text:\n----------\n{doc_text}\n----------\n\n"
        f"Return ONLY a JSON object with exactly these keys: {keys}. "
        "For a table field the value is an array of row objects. "
        "A simple field's value usually appears right after its label, or in the "
        "same markdown table row as its label — check table cells carefully. "
        "Use null only when the field truly is not present. Copy values exactly as "
        "written in the document text — do not guess, translate, or invent digits."
    )


def _unwrap_scalar(val):
    """Models occasionally wrap a scalar as [{'label': value}] when the value
    sat inside a table on the page — unwrap to the innermost value."""
    for _ in range(3):
        if isinstance(val, list):
            val = val[0] if val else None
        elif isinstance(val, dict):
            val = next(iter(val.values()), None)
        else:
            break
    return val


def _parse_json(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def _clean_table(rows, columns: list[dict]) -> list[dict]:
    if not isinstance(rows, list):
        return []
    col_types = {c["name"]: c.get("type", "text") for c in columns}
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cleaned = {}
        for name, ctype in col_types.items():
            val = row.get(name)
            cleaned[name] = _coerce_number(val) if ctype == "number" else val
        out.append(cleaned)
    return out


def extract_document(pages_dir: Path, template: dict, model: str) -> dict:
    """Extract all template fields from one (already rendered) document.

    `pages_dir` is the directory holding that document's page_<i>.png files.
    The template may carry its own `extract_mode` ("vlm" / "thai-ocr"),
    falling back to the server-wide LOCALOCR_EXTRACT_MODE.
    """
    mode = template.get("extract_mode") or config.EXTRACT_MODE
    # Group fields by the page they live on, preserving order.
    by_page: dict[int, list[dict]] = {}
    for f in template["fields"]:
        by_page.setdefault(f.get("page", 0), []).append(f)

    result_fields: dict = {f["name"]: None for f in template["fields"]}

    for page_idx, fields in sorted(by_page.items()):
        try:
            img = load_page_image(pages_dir, page_idx)
        except FileNotFoundError:
            continue
        png = image_to_png_bytes(img)
        doc_text = None
        if mode == "thai-ocr":
            # Stage 1: Typhoon OCR transcribes the page (Thai-accurate);
            # the PDF text layer, when present, serves as its anchor hint.
            anchor = ""
            txt = pages_dir / f"page_{page_idx}.txt"
            if txt.exists():
                anchor = txt.read_text(encoding="utf-8")[:4000]
            doc_text = ocr_page(png, anchor)
            # Stage 2: the general model pulls the fields out of the text.
            raw = text_extract(_build_text_prompt(fields, doc_text), model=model, as_json=True)
        else:
            raw = vision_extract(png, _build_prompt(fields), model=model, as_json=True)
        data = _parse_json(raw)

        # Scalar fields the model missed get one focused retry against the OCR
        # text — a short field list reliably finds values the big combined
        # prompt overlooked.
        if doc_text:
            missed = [
                f
                for f in fields
                if f["type"] != "table" and _unwrap_scalar(data.get(f["name"])) in (None, "")
            ]
            if missed:
                retry = _parse_json(
                    text_extract(_build_text_prompt(missed, doc_text), model=model, as_json=True)
                )
                for f in missed:
                    if retry.get(f["name"]) not in (None, ""):
                        data[f["name"]] = retry[f["name"]]

        for f in fields:
            val = data.get(f["name"])
            if f["type"] == "table":
                result_fields[f["name"]] = _clean_table(val, f.get("columns", []))
                continue
            val = _unwrap_scalar(val)
            if f["type"] == "number":
                result_fields[f["name"]] = _coerce_number(val) if val is not None else None
            else:
                if isinstance(val, str):
                    val = val.strip() or None
                result_fields[f["name"]] = val

    return {"fields": result_fields}
