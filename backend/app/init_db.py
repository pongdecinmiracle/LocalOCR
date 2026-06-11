"""One-shot DB initialization, run by entrypoint.sh before workers start.

Creating tables once here avoids a race where multiple uvicorn workers try to
CREATE TABLE simultaneously against a fresh database.
"""
from __future__ import annotations

from app.config import ensure_dirs
from app.database import Base, engine
from app import models  # noqa: F401  (registers tables on Base.metadata)


def main() -> None:
    ensure_dirs()
    Base.metadata.create_all(bind=engine)
    print("LocalOCR: database schema is ready.")


if __name__ == "__main__":
    main()
