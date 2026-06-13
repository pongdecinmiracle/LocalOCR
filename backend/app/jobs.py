"""DB-backed extraction job queue.

POST /api/extract enqueues a row in extraction_jobs and returns immediately;
worker threads (one per uvicorn worker process) claim queued jobs with
SELECT ... FOR UPDATE SKIP LOCKED and run them, committing progress after every
document. Because all state lives in PostgreSQL, any process can serve the
polling endpoint, several jobs can run concurrently across processes, and the
HTTP workers stay free for interactive requests — this is what lets 10+ users
share the app while extractions are running.
"""
from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.database import SessionLocal
from app.extract import extract_document
from app.models import ExtractionJob, Upload
from app.services import templates as template_svc
from app.storage import user_pages

log = logging.getLogger("localocr.jobs")

_stop = threading.Event()
_thread: threading.Thread | None = None

POLL_SECONDS = 1.0


# ---------------- API used by the router ----------------
def create_job(db: Session, user_id: str, template_id: str, upload_ids: list[str]) -> dict:
    now = int(time.time())
    job = ExtractionJob(
        user_id=user_id,
        template_id=template_id,
        upload_ids=upload_ids,
        total=len(upload_ids),
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job_public(job)


def get_job(db: Session, user_id: str, job_id: str) -> dict | None:
    job = db.get(ExtractionJob, job_id)
    if not job or job.user_id != user_id:
        return None
    return job_public(job)


def job_public(job: ExtractionJob) -> dict:
    return {
        "job_id": job.id,
        "status": job.status,
        "total": job.total,
        "done": job.done,
        "current_file": job.current_file,
        "results": job.results,
        "error": job.error,
    }


# ---------------- worker ----------------
def _claim(db: Session) -> str | None:
    q = (
        select(ExtractionJob)
        .where(ExtractionJob.status == "queued")
        .order_by(ExtractionJob.created_at)
        .limit(1)
    )
    if db.get_bind().dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    job = db.scalars(q).first()
    if not job:
        db.rollback()
        return None
    job.status = "running"
    job.updated_at = int(time.time())
    db.commit()
    return job.id


def _fail(db: Session, job: ExtractionJob, message: str) -> None:
    job.status = "error"
    job.error = message[:500]
    job.current_file = None
    job.updated_at = int(time.time())
    db.commit()


def run_job(job_id: str) -> None:
    """Execute one claimed job, committing progress after each document."""
    db = SessionLocal()
    try:
        job = db.get(ExtractionJob, job_id)
        if not job:
            return
        template = template_svc.get_template(db, job.user_id, job.template_id)
        if not template:
            _fail(db, job, "Template no longer exists.")
            return

        results: list[dict] = []
        for uid in job.upload_ids:
            row = db.get(Upload, uid)
            if not row or row.user_id != job.user_id:
                job.done += 1
                db.commit()
                continue
            job.current_file = row.filename
            job.updated_at = int(time.time())
            db.commit()

            res = extract_document(user_pages(job.user_id) / uid, template, config.VISION_MODEL)
            results.append({"upload_id": uid, "file": row.filename, "fields": res["fields"]})

            job.done += 1
            job.results = list(results)  # new list so the JSON column registers the change
            job.updated_at = int(time.time())
            db.commit()

        job.status = "done"
        job.current_file = None
        job.updated_at = int(time.time())
        db.commit()
        log.info("job done: id=%s user=%s docs=%d", job.id, job.user_id, len(results))
    except Exception as e:
        log.exception("job failed: id=%s", job_id)
        try:
            job = db.get(ExtractionJob, job_id)
            if job:
                _fail(db, job, str(e))
        except Exception:
            log.exception("could not mark job failed: id=%s", job_id)
    finally:
        db.close()


def _worker_loop() -> None:
    log.info("extraction worker started")
    while not _stop.is_set():
        job_id = None
        try:
            db = SessionLocal()
            try:
                job_id = _claim(db)
            finally:
                db.close()
            if job_id:
                run_job(job_id)
        except Exception:
            log.exception("worker loop error")
        if not job_id:
            _stop.wait(POLL_SECONDS)
    log.info("extraction worker stopped")


def start_worker() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_worker_loop, name="extract-worker", daemon=True)
    _thread.start()


def stop_worker() -> None:
    _stop.set()
