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
    "fenced_action",
    "deployment_scope",
]


def deployment_scope() -> dict[str, Any]:
    """Declared applicability boundary (S6).

    The lease is enforced by OS file creation/replace atomicity. It holds
    only where all executor processes share ONE filesystem volume on ONE
    host (or a strongly consistent shared volume with atomic create).
    It is NOT universal distributed ownership across hosts, containers
    with isolated volumes, or network filesystems without atomic O_EXCL.
    """
    return {
        "mechanism": "atomic file create (O_CREAT|O_EXCL) + atomic replace",
        "scope": "single host with one shared filesystem volume",
        "not_scope": "multi-host, isolated container volumes, or NFS without atomic O_EXCL",
        "version": LEASE_VERSION,
    }


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
                       "fence": _next_fence(path, now),
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


def _next_fence(path: str, now: float) -> int:
    """Monotonic generation: max(existing fence, 0) + 1 (best-effort read)."""
    current = _payload(path)
    try:
        return int(current.get("fence", 0)) + 1 if current else 1
    except (TypeError, ValueError, AttributeError):
        return 1


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
            "fence": current.get("fence"),
            "version": current.get("version")}


def fenced_action(path: str, owner: str, ttl_s: float, fn: Any,
                  *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run fn inside verified lease ownership (S6 critical-section fencing).

    Verifies the owner token immediately BEFORE and AFTER fn: a takeover in
    between reports FENCED_OUT instead of blessing results produced without
    ownership. The lease is released afterward either way (best-effort).
    fn exceptions release the lease, then report FENCED_ACTION_FAILED —
    never a success.
    """
    acquired = acquire_lease(path, owner, ttl_s)
    if not acquired.get("ok"):
        return {"ok": False, "reason": acquired.get("reason", "LEASE_HELD"),
                "holder": acquired.get("holder")}
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:
        release_lease(path, acquired["token"])
        return {"ok": False, "reason": "FENCED_ACTION_FAILED",
                "detail": f"{type(exc).__name__}: {exc}"}
    post = heartbeat_lease(path, acquired["token"], ttl_s)
    release_lease(path, acquired["token"])
    if not post.get("ok"):
        return {"ok": False, "reason": "FENCED_OUT",
                "detail": "ownership lost during the critical section"}
    return {"ok": True, "result": result}
