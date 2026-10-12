import hashlib
import math
from collections import deque
from collections.abc import Callable
from threading import Lock
from time import monotonic

from app.core.config import Settings
from app.core.errors import AppError


class LoginRateLimiter:
    """Per-process, bounded sliding-window limiter. Keys store only identifier hashes."""

    def __init__(self, settings: Settings, clock: Callable[[], float] = monotonic) -> None:
        self.settings = settings
        self.clock = clock
        self.buckets: dict[str, deque[float]] = {}
        self.lock = Lock()
        self.last_cleanup = 0.0

    def check(self, ip: str, employee_id: str) -> None:
        now = self.clock()
        window = self.settings.login_rate_limit_window_seconds
        keys = (
            (hashlib.sha256(f"ip:{ip}".encode()).hexdigest(), self.settings.login_rate_limit_ip),
            (
                hashlib.sha256(f"employee:{employee_id.casefold()}".encode()).hexdigest(),
                self.settings.login_rate_limit_employee,
            ),
        )
        with self.lock:
            if now - self.last_cleanup >= window:
                self.buckets = {k: v for k, v in self.buckets.items() if v and v[-1] > now - window}
                self.last_cleanup = now
            for key, limit in keys:
                if key not in self.buckets and len(self.buckets) >= 10000:
                    raise AppError(
                        429, "RATE_LIMITED", "Too many sign-in attempts. Try again later."
                    )
                bucket = self.buckets.setdefault(key, deque())
                while bucket and bucket[0] <= now - window:
                    bucket.popleft()
                if len(bucket) >= limit:
                    retry = max(1, math.ceil(bucket[0] + window - now))
                    raise AppError(
                        429,
                        "RATE_LIMITED",
                        "Too many sign-in attempts. Try again later.",
                        headers={"Retry-After": str(retry)},
                    )
            for key, _ in keys:
                self.buckets[key].append(now)
