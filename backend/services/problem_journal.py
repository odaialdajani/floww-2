"""Bounded local issue history and observed recovery results. No code execution."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import sys
import threading
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

KINDS = {"browser_error", "read_error", "slow_read", "screen_lag", "socket_error", "recovery", "server_log", "slow_request", "failed_request"}
NAMES = {"Error", "TypeError", "ReferenceError", "RangeError", "SyntaxError", "AbortError", "NetworkError", "Unknown"}


def redact(value):
    text = str(value)[:2000]
    text = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [hidden]", text)
    text = re.sub(r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|cookie|authorization)\s*[=:]\s*)[^\s,;]+", r"\1[hidden]", text)
    text = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[hidden]", text)
    text = re.sub(r"\b[A-Za-z0-9_=-]{40,}\b", "[hidden]", text)
    return text[:400]


def safe_route(value):
    route = str(value or "").split("?", 1)[0].split("#", 1)[0]
    if not route.startswith("/") or len(route) > 200:
        return ""
    return re.sub(r"[A-Za-z0-9_-]{40,}", "[hidden]", route)


def problem_label(message):
    """Only fixed descriptions are persisted from arbitrary server log text."""
    text = str(message).lower()
    for terms, label in (
        (("budget", "rate limit", "429"), "Provider allowance reached"),
        (("timeout", "timed out"), "Time limit reached"),
        (("not installed", "no module", "missing"), "A required component is missing"),
        (("unavailable", "refused", "connection"), "Data or connection unavailable"),
        (("stale",), "Old data reported"),
        (("failed", "error", "exception"), "App operation failed"),
    ):
        if any(term in text for term in terms):
            return label
    return "App warning"


class DurableEvents(RotatingFileHandler):
    def handleError(self, record):
        raise OSError("Problem event log could not be saved") from None


class ProblemJournal:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.events = DurableEvents(self.directory / "events.jsonl", maxBytes=2_000_000,
                                         backupCount=3, encoding="utf-8")
        self.events.setFormatter(logging.Formatter("%(message)s"))
        self.path = self.directory / "summary.json"
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = {"issues": {}, "recoveries": {}, "total_events": 0, "started_at": self.now()}
        self.state.setdefault("processed_events", {})
        self.recent = []

    @staticmethod
    def now():
        return datetime.now(UTC).isoformat()

    def record(self, event):
        kind = event.get("kind")
        if kind not in KINDS:
            raise ValueError("Unsupported problem kind")
        row = {"kind": kind, "at": self.now(), "route": safe_route(event.get("route")),
               "name": event.get("name") if event.get("name") in NAMES else "Unknown"}
        for key in ("status", "duration_ms"):
            value = event.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 3_600_000:
                row[key] = round(value)
        row["method"] = event.get("method") if event.get("method") in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"} else ""
        if kind == "recovery":
            row["result"] = event.get("result") if event.get("result") in {"succeeded", "failed"} else "attempted"
        if kind == "server_log":
            row["message"] = problem_label(event.get("message", ""))
            row["source"] = re.sub(r"[^A-Za-z0-9_.]", "", str(event.get("source", "")))[:100]
        fingerprint = {k: row.get(k) for k in ("kind", "route", "method", "status", "name", "source")}
        if kind == "server_log":
            fingerprint["message"] = re.sub(r"\b\d+(?:\.\d+)?\b", "#", row["message"])
        identity = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:16]
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not re.fullmatch(r"[a-f0-9-]{36}", event_id):
            event_id = None
        if event_id:
            row["event_id"] = event_id
        with self.lock:
            previous_state = copy.deepcopy(self.state)
            previous_recent = list(self.recent)
            try:
                processed = self.state["processed_events"]
                if event_id and event_id in processed:
                    return
                if event_id:
                    processed[event_id] = row["at"]
                    if len(processed) > 5000:
                        del processed[min(processed, key=processed.get)]
                self.events.emit(logging.makeLogRecord({"msg": json.dumps(row), "levelno": logging.INFO}))
                self.state["total_events"] += 1
                target = "recoveries" if kind == "recovery" else "issues"
                entries = self.state[target]
                previous = entries.get(identity, {})
                updated = {**row, "count": previous.get("count", 0) + 1, "first_at": previous.get("first_at", row["at"])}
                if kind == "recovery":
                    for result in ("attempted", "succeeded", "failed"):
                        updated[result] = previous.get(result, 0) + (row["result"] == result)
                updated["worst_duration_ms"] = max(previous.get("worst_duration_ms", 0), row.get("duration_ms", 0))
                entries[identity] = updated
                if len(entries) > 300:
                    del entries[min(entries, key=lambda key: entries[key]["at"])]
                self.recent = [row, *self.recent[:19]]
                pending = self.path.with_suffix(".pending")
                pending.write_text(json.dumps(self.state), encoding="utf-8")
                pending.replace(self.path)
            except Exception:
                self.state = previous_state
                self.recent = previous_recent
                raise

    def summary(self):
        with self.lock:
            issues = sorted(self.state["issues"].values(), key=lambda row: row["at"], reverse=True)
            return {"status": "recording", "started_at": self.state["started_at"],
                    "total_events": self.state["total_events"], "issues": issues[:30],
                    "recurring": sum(row["count"] > 1 for row in issues),
                    "recoveries": list(self.state["recoveries"].values()),
                    "updated_at": self.now(), "recent": list(self.recent),
                    "limits": "Local records of observed problems. A successful retry does not prove fresh data or a permanent fix."}

    def close(self):
        self.events.close()


_journal = None
_init_lock = threading.Lock()


def test_context():
    return "pytest" in sys.modules or os.getenv("TESTING", "").lower() in {"1", "true", "yes"}


def journal():
    global _journal
    if test_context() and not os.getenv("FLOWW_PROBLEM_LOG_DIR"):
        raise RuntimeError("Tests require an isolated problem log")
    with _init_lock:
        if _journal is None:
            directory = os.getenv("FLOWW_PROBLEM_LOG_DIR")
            if not directory and test_context():
                raise RuntimeError("Tests require an isolated problem log")
            if not directory:
                directory = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "FLOWW" / "problems"
            _journal = ProblemJournal(directory)
    return _journal


def record_problem(event):
    try:
        journal().record(event)
        return True
    except Exception:
        # Problem reporting cannot interrupt market reads or report recursively.
        return False


class ProblemHandler(logging.Handler):
    def emit(self, record):
        record_problem({"kind": "server_log", "source": str(record.name or "unknown") + "." + str(record.funcName or "unknown"),
                        "message": record.getMessage(), "name": type(record.exc_info[1]).__name__ if record.exc_info else "Unknown"})


def install_problem_logging():
    if test_context() and not os.getenv("FLOWW_PROBLEM_LOG_DIR"):
        return
    root = logging.getLogger()
    if not any(isinstance(handler, ProblemHandler) for handler in root.handlers):
        root.addHandler(ProblemHandler(logging.WARNING))
