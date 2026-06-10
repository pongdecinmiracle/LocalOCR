"""Simple JSON-file storage for layout templates.

A template captures named field boxes over a document layout so the same
extraction can be replayed on future documents of the same kind.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import TEMPLATES


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "template"


def list_templates() -> list[dict]:
    out = []
    for f in sorted(TEMPLATES.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    out.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return out


def get_template(template_id: str) -> dict | None:
    f = TEMPLATES / f"{template_id}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def save_template(data: dict) -> dict:
    """Create or update a template. `data` must contain name + fields[]."""
    tid = data.get("id") or f"{_slug(data.get('name', 'template'))}_{uuid.uuid4().hex[:8]}"
    data["id"] = tid
    data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Normalize fields
    norm_fields = []
    for fld in data.get("fields", []):
        nf = {
            "id": fld.get("id") or uuid.uuid4().hex[:8],
            "name": fld["name"],
            "label": fld.get("label") or fld["name"],
            "type": fld.get("type", "text"),
            "page": int(fld.get("page", 0)),
            "box": {
                "x": float(fld["box"]["x"]),
                "y": float(fld["box"]["y"]),
                "w": float(fld["box"]["w"]),
                "h": float(fld["box"]["h"]),
            },
        }
        if nf["type"] == "table":
            nf["columns"] = [
                {"name": c["name"], "type": c.get("type", "text")}
                for c in fld.get("columns", [])
            ]
        norm_fields.append(nf)
    data["fields"] = norm_fields

    (TEMPLATES / f"{tid}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return data


def delete_template(template_id: str) -> bool:
    f = TEMPLATES / f"{template_id}.json"
    if f.exists():
        f.unlink()
        return True
    return False
