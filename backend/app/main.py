"""LocalOCR backend service — API only (the frontend is served by nginx).

Accounts and templates live in PostgreSQL; uploaded files and rendered pages
live on a shared data volume. The vision model runs in a separate Ollama
service. See docker-compose.yml.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import ensure_dirs
from app.database import Base, SessionLocal, engine
from app.routers import admin, auth, extraction, templates, uploads
from app.services import users as user_svc


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tables are normally created by `python -m app.init_db` in entrypoint.sh;
    # create_all here is a harmless idempotent safety net for non-container runs.
    ensure_dirs()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user_svc.ensure_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(title="LocalOCR", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(uploads.router)
app.include_router(templates.router)
app.include_router(extraction.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
