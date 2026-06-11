"""ORM models: users, templates and upload metadata.

Templates and upload page metadata are stored as JSON columns because they are
nested, schemaless-ish documents that the rest of the app already consumes as
plain dicts/lists. The flat columns (name, created_at) exist for querying and
ordering.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    # Lowercased username, used to enforce case-insensitive uniqueness.
    username_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    pages: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
