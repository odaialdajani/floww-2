"""
backend/services/execution_lease.py — atomic single-executor lease (S3).

DuckDB permits one writer; threaded or advisory checks inside one process
cannot exclude a second process. This module enforces single-executor
ownership at the OS boundary every process on this host honors:

- Acquisition is one atomic filesystem step (O_CREAT|O_EXCL). Two racers
  cannot both succeed — the kernel decides, not application logic.
- The lease payload carries owner + expiry. A crashed holder stops
  heartbeating; after expiry another owner may steal it (stale-owner
  recovery). Steal-before-expiry refuses LEASE_HELD.
- Release requires the owner token. Foreign release refuses LEASE_NOT_OWNER
  and never deletes another owner's lease.
- Heartbeat extends only by the owning token; expired leases cannot be
  heartbeated back (must re-acquire, proving liveness again).

Integration point (proposal, NOT wired): the executor holds a lease across
its submit critical section; Zed/Nav review before any wiring. No live
calls, no venue flags, no broker use in this module.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

LEASE_VERSION = "execution-lease.v1"
DEFAULT_TTL_S = 120.0

__all__ = [
    "LEASE_VERSION",
    "DEFAULT_TTL_S",
    "acquire_lease",
    "heartbeat_lease",
    "release_lease",
    "read_lease",
]


def _payload(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _expired(payload: dict[str, Any], now: float) -> bool:
    try:
        return float(payload.get("expires_at", 0.0)) <= now
    except (TypeError, ValueError):
        return True


def acquire_lease(path: str, owner: str, ttl_s: float = DEFAULT_TTL_S) -> dict[str, Any]:
    """Atomically acquire the executor lease (one kernel-decided winner)."""
    if not str(path or "").strip() or not str(owner or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    try:
        ttl = float(ttl_s)
        if not (0 < ttl < 86400):
            return {"ok": False, "reason": "BAD_CONTRACT"}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "BAD_CONTRACT"}
    now = time.time()
    token = uuid.uuid4().hex
    body = json.dumps({"owner": str(owner), "token": token,
                       "acquired_at": now, "expires_at": now + ttl,
                       "version": LEASE_VERSION})
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        current = _payload(path)
        if current is None:
            return {"ok": False, "reason": "LEASE_CORRUPT_HOLDER"}
        if not _expired(current, time.time()):
            return {"ok": False, "reason": "LEASE_HELD",
                    "holder": current.get("owner")}
        try:
            os.replace(_stage(path, body), path)
        except OSError:
            return {"ok": False, "reason": "LEASE_HELD"}
        return {"ok": True, "owner": str(owner), "token": token,
                "stole_expired": True}
    except OSError:
        return {"ok": False, "reason": "LEASE_IO_ERROR"}
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
    except OSError:
        return {"ok": False, "reason": "LEASE_IO_ERROR"}
    return {"ok": True, "owner": str(owner), "token": token,
            "stole_expired": False}


def _stage(path: str, body: str) -> str:
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    return tmp


def heartbeat_lease(path: str, token: str, ttl_s: float = DEFAULT_TTL_S) -> dict[str, Any]:
    """Extend an owned, unexpired lease. Foreign/expired tokens refuse."""
    if not str(token or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    try:
        ttl = float(ttl_s)
        if not (0 < ttl < 86400):
            return {"ok": False, "reason": "BAD_CONTRACT"}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "BAD_CONTRACT"}
    current = _payload(path)
    if current is None:
        return {"ok": False, "reason": "LEASE_ABSENT"}
    if current.get("token") != token:
        return {"ok": False, "reason": "LEASE_NOT_OWNER"}
    if _expired(current, time.time()):
        return {"ok": False, "reason": "LEASE_EXPIRED"}
    now = time.time()
    current["expires_at"] = now + ttl
    try:
        os.replace(_stage(path, json.dumps(current)), path)
    except OSError:
        return {"ok": False, "reason": "LEASE_IO_ERROR"}
    return {"ok": True}


def release_lease(path: str, token: str) -> dict[str, Any]:
    """Release an owned lease. Foreign tokens refuse without deleting."""
    if not str(token or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    current = _payload(path)
    if current is None:
        return {"ok": False, "reason": "LEASE_ABSENT"}
    if current.get("token") != token:
        return {"ok": False, "reason": "LEASE_NOT_OWNER"}
    try:
        os.unlink(path)
    except OSError:
        return {"ok": False, "reason": "LEASE_IO_ERROR"}
    return {"ok": True}


def read_lease(path: str) -> dict[str, Any]:
    """Inspect the lease without mutating (owner token redacted)."""
    current = _payload(path)
    if current is None:
        return {"present": False}
    return {"present": True, "owner": current.get("owner"),
            "expired": _expired(current, time.time()),
            "version": current.get("version")}
