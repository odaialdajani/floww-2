"""backend/services/rate_limit_tracker.py"""

from __future__ import annotations

import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class RateLimitTracker:
    def __init__(self, per_minute: int = 5, per_day: int = 500) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self._minute_window: deque[float] = deque()
        self._day_window: deque[float] = deque()

    def _prune(self, now: float | None = None) -> None:
        if now is None:
            now = time.time()
        minute_ago = now - 60
        day_ago = now - 86400
        while self._minute_window and self._minute_window[0] <= minute_ago:
            self._minute_window.popleft()
        while self._day_window and self._day_window[0] <= day_ago:
            self._day_window.popleft()

    def can_call(self) -> bool:
        self._prune()
        return (len(self._minute_window) < self.per_minute and len(self._day_window) < self.per_day)

    def record_call(self, ts: float | None = None) -> None:
        if ts is None:
            ts = time.time()
        self._minute_window.append(ts)
        self._day_window.append(ts)

    @property
    def remaining_minute(self) -> int:
        self._prune()
        return max(0, self.per_minute - len(self._minute_window))

    @property
    def remaining_day(self) -> int:
        self._prune()
        return max(0, self.per_day - len(self._day_window))

    def get_status(self) -> dict[str, dict[str, int]]:
        self._prune()
        return {
            "per_minute": {"limit": self.per_minute, "used": len(self._minute_window), "remaining": self.remaining_minute},
            "per_day": {"limit": self.per_day, "used": len(self._day_window), "remaining": self.remaining_day},
        }


av_rate_tracker = RateLimitTracker(per_minute=5, per_day=500)
