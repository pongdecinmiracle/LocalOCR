"""Apply database migrations, run by entrypoint.sh before workers start.

Handles three cases:
  - fresh database            -> run all migrations
  - pre-Alembic database      -> stamp the matching revision, then upgrade
  - already-managed database  -> upgrade to head

Also fails any jobs that were queued/running when the server last stopped, so
clients never poll a job that no worker will ever finish.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.config import ensure_dirs
from app.database import engine

_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def main() -> None:
    ensure_dirs()
    cfg = Config(str(_INI))

    insp = inspect(engine)
    if not insp.has_table("alembic_version") and insp.has_table("users"):
        # Database predates Alembic: stamp the revision matching its schema.
        cols = {c["name"] for c in insp.get_columns("users")}
        if "last_seen" in cols:
            rev = "0003"
        elif "token_version" in cols:
            rev = "0002"
        else:
            rev = "0001"
        print(f"LocalOCR: adopting existing schema at revision {rev}")
        command.stamp(cfg, rev)

    command.upgrade(cfg, "head")

    # Orphaned jobs from a previous run can never complete — fail them.
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE extraction_jobs SET status='error', "
                "error='Interrupted by a server restart — run the extraction again.' "
                "WHERE status IN ('queued', 'running')"
            )
        )
    print("LocalOCR: database schema is ready.")


if __name__ == "__main__":
    main()
