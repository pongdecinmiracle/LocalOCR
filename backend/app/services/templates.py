"""Layout templates, backed by the database.

A template captures named field boxes over a document layout so the same
extraction can be replayed on future documents of the same kind. The full
template document is stored in a JSON column (`data`); the rest of the app
consumes it as a plain dict, exactly as before.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Template


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "template"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_templates(db: Session, user_id: str) -> list[dict]:
    rows = db.scalars(
        select(Template)
        .where(Template.user_id == user_id)
        .order_by(Template.created_at.desc())
    ).all()
    return [r.data for r in rows]


def get_template(db: Session, user_id: str, template_id: str) -> dict | None:
    row = db.get(Template, template_id)
    if not row or row.user_id != user_id:
        return None
    return row.data


def save_template(db: Session, user_id: str, data: dict) -> dict:
    """Create or update a template. `data` must contain name + fields[]."""
    tid = data.get("id") or f"{_slug(data.get('name', 'template'))}_{uuid.uuid4().hex[:8]}"
    data["id"] = tid

    existing = db.get(Template, tid)
    if existing and existing.user_id != user_id:
        # Don't let one user overwrite another's template by guessing an id.
        raise ValueError("template not found")

    created = (existing.created_at if existing else None) or data.get("created_at") or _now()
    data["created_at"] = created
    data["updated_at"] = _now()

    # Optional per-template extraction engine; absent/invalid means "follow
    # the server-wide LOCALOCR_EXTRACT_MODE default".
    if data.get("extract_mode") not in ("vlm", "thai-ocr"):
        data.pop("extract_mode", None)

    # Normalize fields (same shape the editor and extractor expect).
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

    if existing:
        existing.name = data.get("name", "")
        existing.data = data
        existing.created_at = created
        existing.updated_at = data["updated_at"]
    else:
        db.add(
            Template(
                id=tid,
                user_id=user_id,
                name=data.get("name", ""),
                data=data,
                created_at=created,
                updated_at=data["updated_at"],
            )
        )
    db.commit()
    return data


def delete_template(db: Session, user_id: str, template_id: str) -> bool:
    row = db.get(Template, template_id)
    if not row or row.user_id != user_id:
        return False
    db.delete(row)
    db.commit()
    return True
