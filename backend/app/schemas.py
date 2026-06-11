"""Request bodies for the API."""
from __future__ import annotations

from pydantic import BaseModel


class Credentials(BaseModel):
    username: str
    password: str


class ExtractRequest(BaseModel):
    template_id: str
    upload_ids: list[str]


class ExportRequest(BaseModel):
    template_id: str
    results: list[dict]


class AdminCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class PasswordReset(BaseModel):
    password: str


class AdminToggle(BaseModel):
    is_admin: bool
