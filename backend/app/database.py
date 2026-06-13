"""SQLAlchemy engine, session factory and declarative base."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

# SQLite is only used by the test suite; TestClient may touch the session from
# worker threads, so relax its same-thread check.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# pool_pre_ping recycles connections dropped by the DB between requests.
engine = create_engine(
    DATABASE_URL, pool_pre_ping=True, future=True, connect_args=_connect_args
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()
