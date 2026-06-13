"""Test fixtures: SQLite-backed app with a temp data dir.

Environment must be configured before any app module is imported, since
config.py reads env vars at import time.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

_tmp = Path(tempfile.mkdtemp(prefix="localocr-test-"))
os.environ["LOCALOCR_DATA_DIR"] = str(_tmp)
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["LOCALOCR_SECRET_KEY"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import login_limiter  # noqa: E402


@pytest.fixture()
def client():
    """A TestClient against a freshly reset database."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    login_limiter._failures.clear()
    # No context manager: lifespan (worker thread) intentionally not started.
    return TestClient(app)


@pytest.fixture()
def second_client():
    return TestClient(app)


def register(c: TestClient, username: str = "alice", password: str = "secret123"):
    return c.post("/api/register", json={"username": username, "password": password})
