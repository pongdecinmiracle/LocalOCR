"""In-memory failed-login limiter (per worker process).

Tracks consecutive failures per (client IP, username) and locks the pair out
after too many. Per-process state is approximate when several uvicorn workers
run, so nginx adds a shared per-IP request-rate limit on /api/login as the
first line of defence; this limiter adds the per-account lockout behind it.
"""
from __future__ import annotations

import threading
import time

from app import config


class FailureLimiter:
    def __init__(self, max_failures: int | None = None, lockout: int | None = None):
        self.max_failures = max_failures or config.LOGIN_MAX_FAILURES
        self.lockout = lockout or config.LOGIN_LOCKOUT_SECONDS
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}

    def retry_after(self, key: str) -> int:
        """Seconds until this key may try again (0 = allowed now)."""
        now = time.time()
        with self._lock:
            stamps = [t for t in self._failures.get(key, []) if now - t < self.lockout]
            self._failures[key] = stamps
            if len(stamps) >= self.max_failures:
                return int(self.lockout - (now - stamps[0])) + 1
            return 0

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._failures.setdefault(key, []).append(time.time())
            # Opportunistic cleanup so the map can't grow unbounded.
            if len(self._failures) > 10_000:
                cutoff = time.time() - self.lockout
                self._failures = {
                    k: v for k, v in self._failures.items() if v and v[-1] > cutoff
                }

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = FailureLimiter()
