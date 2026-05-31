"""backend/tests/services/test_rate_limit_tracker.py"""
from __future__ import annotations

import time

from services.rate_limit_tracker import RateLimitTracker


def make_tracker(minute: int = 5, day: int = 25) -> RateLimitTracker:
    return RateLimitTracker(per_minute=minute, per_day=day)


class TestQuota:
    def test_initial_can_call_is_true(self):
        assert make_tracker().can_call() is True

    def test_record_call_counts_toward_both_limits(self):
        t = make_tracker()
        for _ in range(3):
            t.record_call()
        assert t.remaining_minute == 2
        assert t.remaining_day == 22

    def test_day_quota_exhausted(self):
        t = make_tracker()
        for _ in range(25):
            t.record_call()
        assert t.remaining_day == 0
        assert t.can_call() is False

    def test_minute_quota_exhausted(self):
        t = make_tracker()
        for _ in range(5):
            t.record_call()
        assert t.remaining_minute == 0

    def test_combined_limit_blocks(self):
        t = make_tracker(minute=2, day=3)
        for _ in range(3):
            t.record_call()
        assert t.can_call() is False


class TestPruning:
    def test_stale_minute_entries_pruned(self):
        t = make_tracker()
        now = time.time()
        for _ in range(3):
            t._minute_window.append(now - 120)
        assert len(t._minute_window) == 3
        t._prune(now)
        assert len(t._minute_window) == 0

    def test_recent_minute_entries_kept(self):
        t = make_tracker()
        now = time.time()
        t._minute_window.append(now - 30)
        t._prune(now)
        assert len(t._minute_window) == 1

    def test_stale_day_entries_pruned(self):
        t = make_tracker()
        now = time.time()
        t._day_window.append(now - 86401)
        t._prune(now)
        assert len(t._day_window) == 0

    def test_recent_day_entries_kept(self):
        t = make_tracker()
        now = time.time()
        t._day_window.append(now - 86400 + 1)
        t._prune(now)
        assert len(t._day_window) == 1

    def test_mixed_ages(self):
        t = make_tracker()
        now = time.time()
        t._day_window.append(now - 86401)
        t._day_window.append(now - 43200)
        t._prune(now)
        assert len(t._day_window) == 1
        assert t._day_window[0] == now - 43200


class TestConcurrent:
    def test_record_call_threadsafe(self):
        import asyncio
        t = make_tracker(minute=1000, day=1000)

        async def main():
            for _ in range(100):
                t.record_call()

        asyncio.run(main())
        assert len(t._day_window) == 100
        assert len(t._minute_window) == 100
