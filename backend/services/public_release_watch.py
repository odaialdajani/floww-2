"""Detect official Public documentation changes without executing remote code.

The reviewed baseline is committed data. New releases never approve themselves
or turn on trading capabilities. Checks are cached daily; failed checks remain
unknown, not "up to date". All requests are to public documentation, no secrets.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx

BASE = "https://public.com"
CHANGELOG = "/api/docs/changelog"
BASELINE = Path(__file__).resolve().parents[2] / "config" / "public_docs_reviewed.json"
_cached: dict | None = None
_next_check = 0.0
_lock = asyncio.Lock()


class Documentation(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_main = False
        self.hidden = 0
        self.stream_depth = 0
        self.parts = []
        self.resources = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "main":
            self.in_main = True
        # Next.js streams the main body into inert S:n divs after </main>.
        # Read their text as data; never run their hydration scripts.
        if tag == "div":
            if self.stream_depth:
                self.stream_depth += 1
            elif str(attrs.get("id", "")).startswith("S:"):
                self.stream_depth = 1
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag == "a":
            url = urlparse(attrs.get("href", ""))
            if (not url.netloc or url.netloc == "public.com") and url.path.startswith("/api/docs/resources/"):
                self.resources.add(url.path.rstrip("/"))

    def handle_endtag(self, tag):
        if tag == "main":
            self.in_main = False
        if tag == "div" and self.stream_depth:
            self.stream_depth -= 1
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if (self.in_main or self.stream_depth) and not self.hidden and data.strip():
            self.parts.append(data.strip())

    def fingerprint(self):
        text = " ".join(" ".join(self.parts).split())
        if len(text) < 100:
            raise ValueError("Documentation content missing; cannot verify provider releases")
        return hashlib.sha256(text.encode()).hexdigest()


async def fetch_documents(paths: list[str]) -> dict:
    sem = asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        async def one(path):
            if not path.startswith("/api/docs/") or ".." in path:
                raise ValueError("Invalid documentation path")
            async with sem:
                response = await client.get(BASE + path)
                response.raise_for_status()
                document = Documentation()
                document.feed(response.text)
                return path, {"sha256": document.fingerprint(), "resources": sorted(document.resources)}
        return dict(await asyncio.gather(*(one(p) for p in paths)))


def compare_documents(baseline: dict, current: dict) -> dict:
    expected = baseline.get("documents", {})
    if not isinstance(expected, dict) or CHANGELOG not in expected or len(expected) < 2:
        raise ValueError("A reviewed changelog and operation baseline are required")
    try:
        reviewed = datetime.fromisoformat(baseline["reviewed_at"])
        if reviewed.tzinfo is None:
            raise ValueError("Review date needs a timezone")
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Valid documentation review date required") from exc
    changed = sorted(path for path, digest in expected.items()
                     if current.get(path, {}).get("sha256") != digest)
    discovered = set(current.get(CHANGELOG, {}).get("resources", []))
    new = sorted(discovered - set(expected))
    removed = sorted(set(expected) - discovered - {CHANGELOG})
    return {"status": "review_needed" if changed or new or removed else "current",
            "changed_pages": changed, "new_operations": new, "removed_operations": removed,
            "reviewed_at": baseline.get("reviewed_at"),
            "checked_at": datetime.now(UTC).isoformat(),
            "source": BASE + CHANGELOG,
            "automatic_activation": False}


async def get_release_status() -> dict:
    global _cached, _next_check
    async with _lock:
        if _cached is not None and time.monotonic() < _next_check:
            return copy.deepcopy(_cached)
        try:
            baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
            current = await fetch_documents(list(baseline["documents"]))
            _cached = compare_documents(baseline, current)
            _next_check = time.monotonic() + 86400
        except Exception as exc:
            _cached = {"status": "unavailable", "checked_at": datetime.now(UTC).isoformat(),
                       "source": BASE + CHANGELOG, "reason": type(exc).__name__,
                       "automatic_activation": False}
            _next_check = time.monotonic() + 300
        return copy.deepcopy(_cached)
