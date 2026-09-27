"""Pace real Public HTTP requests below the documented 10/second account cap.

This process uses at most eight requests per second, leaving headroom. Other
processes/accounts still share the provider limit; normal 429 cooldown applies.
The scheduler spaces requests rather than allowing a token-bucket burst.
"""
from __future__ import annotations

import asyncio
import time


class RequestPacer:
    def __init__(self, requests_per_second=8.0, clock=None, sleep=None):
        self.interval = 1.0 / min(8.0, max(0.1, float(requests_per_second)))
        self.clock = clock or time.monotonic
        self.sleep = sleep or asyncio.sleep
        self.next_at = 0.0
        self.lock = asyncio.Lock()

    async def wait(self):
        async with self.lock:
            delay = max(0.0, self.next_at - self.clock())
            if delay:
                await self.sleep(delay)
            self.next_at = self.clock() + self.interval


pacer = RequestPacer()


async def pace_request(request):
    if request.url.host == "api.public.com":
        from services.public_budget import budget
        await budget.check_request_allowed()
        await pacer.wait()
        await budget.check_request_allowed()


def note_response(response):
    """Cool every Public endpoint once, including callers that catch the error."""
    if response is None or response.status_code != 429:
        return
    try:
        if response.request.url.host != "api.public.com":
            return
    except (AttributeError, RuntimeError):
        return
    marker = "floww_public_429_recorded"
    if response.extensions.get(marker):
        return
    import math
    from datetime import UTC, datetime
    from email.utils import parsedate_to_datetime

    from services.public_budget import budget

    retry_after = None
    value = response.headers.get("Retry-After")
    if value:
        try:
            delay = float(value)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                delay = float("nan")
        if math.isfinite(delay):
            retry_after = max(1, min(86400, math.ceil(delay)))
    budget.record_429("api.public.com", retry_after=retry_after)
    response.extensions[marker] = True


async def observe_response(response):
    note_response(response)
