"""
backend/services/execution_lease.py — atomic single-executor lease (S3/S6).

DuckDB permits one writer; threaded or advisory checks inside one process
cannot exclude a second process. This module enforces single-executor
ownership at the OS boundary every process on this host honors:

- Fresh acquisition is one atomic filesystem step (O_CREAT|O_EXCL). Two
  racers cannot both succeed — the kernel decides, not application logic.
- Expired-takeover is a compare-and-swap under an inter-process mutex
  (POSIX flock on a sidecar lock file): the winner is decided while
  holding the lock, so exactly one contender observes the expired state
  and claims it. Every other contender observes the new live owner and
  refuses LEASE_HELD. No contender ever receives a success it then loses.
- Heartbeat/release re-verify the owner token while holding the same
  lock, so a stale token can neither extend nor delete a new owner's
  lease (no stale-owner clobber across expiry steal).
- The lease payload carries owner + token + monotonic fence generation.
  The fence survives release/re-acquire via the lock sidecar, so a
  takeover mid-critical-section is detectable downstream. `fenced_action`
  additionally verifies ownership immediately after the work runs and
  reports FENCED_OUT instead of blessing unowned side effects.
- Release requires the owner token. Foreign release refuses LEASE_NOT_OWNER
  and never deletes another owner's lease.
- Heartbeat extends only by the owning token; expired leases cannot be
  heartbeated back (must re-acquire, proving liveness again).

Cross-process exclusion uses POSIX flock on Linux/macOS and a Windows
msvcrt byte-range lock on the same sidecar. Hosts without either lock
fall back to a thread lock and report multi-process safety as unavailable.

Integration point (proposal, NOT wired): the executor holds a lease across
its submit critical section; Zed/Nav review before any wiring. No live
calls, no venue flags, no broker use in this module.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from typing import Any

try:
    import fcntl  # POSIX only (Linux/macOS ship hosts)
except ImportError:  # pragma: no cover — non-POSIX fallback
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt  # Windows file locking
except ImportError:  # POSIX hosts
    msvcrt = None  # type: ignore[assignment]

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
    "effect_with_lease",
    "deployment_scope",
    "MULTIPROCESS_SAFE",
]

MULTIPROCESS_SAFE = fcntl is not None or msvcrt is not None

_THREAD_FALLBACK = threading.Lock()


def deployment_scope() -> dict[str, Any]:
    """Declared applicability boundary (S6).

    The lease is enforced by OS file creation/replace atomicity PLUS a
    OS file-lock sidecar that serializes every read-check-mutate step
    across processes. It holds only where all executor processes share
    ONE filesystem volume on ONE host (or a strongly consistent shared
    volume with atomic create AND working OS file locks). It is NOT universal
    distributed ownership across hosts, containers with isolated volumes,
    or NFS without atomic O_EXCL/file locks. Without either OS locking facility,
    cross-process exclusion is unavailable (see MULTIPROCESS_SAFE).
    """
    return {
        "mechanism": "atomic file create (O_CREAT|O_EXCL) + OS-lock-serialized compare-and-swap",
        "scope": "single host with one shared filesystem volume",
        "not_scope": "multi-host, isolated container volumes, or NFS without atomic O_EXCL",
        "multiprocess_safe": MULTIPROCESS_SAFE,
        "version": LEASE_VERSION,
    }


def _payload(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _lock_path(path: str) -> str:
    return f"{path}.lock"


def _expired(payload: dict[str, Any], now: float) -> bool:
    try:
        return float(payload.get("expires_at", 0.0)) <= now
    except (TypeError, ValueError):
        return True


@contextlib.contextmanager
def _holder_lock(path: str):
    """Inter-process mutex serializing every read-check-mutate step (S6).

    POSIX flock on a sidecar file: two processes cannot both hold it, so
    the expired-takeover compare-and-swap has exactly one winner and
    stale tokens can never clobber a new owner's payload. Yields False
    when the lock file itself cannot be created (fail closed upstream).
    Uses a Windows byte-range lock when fcntl is unavailable. Falls
    back to a thread lock only when neither OS lock exists (same-process
    only; reported via deployment_scope()).
    """
    if fcntl is None and msvcrt is None:
        _THREAD_FALLBACK.acquire()
        try:
            yield True
        finally:
            _THREAD_FALLBACK.release()
        return
    try:
        fd = os.open(_lock_path(path), os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        yield False
        return
    try:
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            else:
                # All contenders lock the same byte, even on an empty file.
                # LK_LOCK retries for a bounded time, then refuses on failure.
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            with contextlib.suppress(OSError):
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                else:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)


def _read_fence_sidecar(path: str) -> int:
    try:
        with open(_lock_path(path) + ".fence", encoding="utf-8") as fh:
            return int(json.load(fh).get("last_fence", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def _write_fence_sidecar(path: str, fence: int) -> None:
    tmp = f"{_lock_path(path)}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"last_fence": int(fence)}))
    os.replace(tmp, _lock_path(path) + ".fence")


def acquire_lease(path: str, owner: str, ttl_s: float = DEFAULT_TTL_S) -> dict[str, Any]:
    """Acquire the executor lease with exactly one winner (S6).

    Fresh create is one kernel-atomic O_CREAT|O_EXCL step. The expired
    takeover is a compare-and-swap serialized by the inter-process lock:
    the winner is decided under the lock, so simultaneous contenders
    cannot all observe the expired state — exactly one acquire returns
    ok True; the rest observe the new live owner and refuse LEASE_HELD.
    """
    if not str(path or "").strip() or not str(owner or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    try:
        ttl = float(ttl_s)
        if not (0 < ttl < 86400):
            return {"ok": False, "reason": "BAD_CONTRACT"}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "BAD_CONTRACT"}
    token = uuid.uuid4().hex
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        return _steal_expired(path, str(owner), token, ttl)
    except OSError:
        return {"ok": False, "reason": "LEASE_IO_ERROR"}
    now = time.time()
    fence = _next_fence(path, now)
    body = json.dumps({"owner": str(owner), "token": token,
                       "acquired_at": now, "expires_at": now + ttl,
                       "fence": fence, "version": LEASE_VERSION})
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
    except OSError:
        _remove_quietly(path)
        return {"ok": False, "reason": "LEASE_IO_ERROR"}
    with _holder_lock(path) as locked:
        # Sidecar is best-effort bookkeeping: the lease above is already
        # valid and owned, so a lock failure here must not report failure
        # for a lease we actually hold (that would strand ownership).
        if locked:
            with contextlib.suppress(OSError):
                _write_fence_sidecar(path, max(fence, _read_fence_sidecar(path)))
    return {"ok": True, "owner": str(owner), "token": token,
            "stole_expired": False}


def _steal_expired(path: str, owner: str, token: str, ttl: float) -> dict[str, Any]:
    """Compare-and-swap takeover of an expired lease, under the lock."""
    with _holder_lock(path) as locked:
        if not locked:
            return {"ok": False, "reason": "LEASE_IO_ERROR"}
        current = _payload(path)
        if current is None:
            # Fresh-create lost the existence race AND the payload is
            # unreadable: refuse rather than guess (a parallel creator may
            # own it). Callers retry acquisition explicitly.
            return {"ok": False, "reason": "LEASE_CORRUPT_HOLDER"}
        if not _expired(current, time.time()):
            return {"ok": False, "reason": "LEASE_HELD",
                    "holder": current.get("owner")}
        now = time.time()
        fence = max(_read_fence_sidecar(path), _fence_of(current)) + 1
        body = json.dumps({"owner": owner, "token": token,
                           "acquired_at": now, "expires_at": now + ttl,
                           "fence": fence, "version": LEASE_VERSION})
        staged = None
        try:
            staged = _stage(path, body)
            os.replace(staged, path)
            _write_fence_sidecar(path, fence)
        except OSError:
            if staged is not None:
                _remove_quietly(staged)
            return {"ok": False, "reason": "LEASE_HELD"}
    return {"ok": True, "owner": owner, "token": token,
            "stole_expired": True}


def _fence_of(payload: dict[str, Any] | None) -> int:
    if not isinstance(payload, dict):
        return 0
    try:
        return int(payload.get("fence", 0))
    except (TypeError, ValueError):
        return 0


def _remove_quietly(path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


def _next_fence(path: str, now: float) -> int:
    """Monotonic generation: max(sidecar, file fence, 0) + 1 (best-effort)."""
    return max(_read_fence_sidecar(path), _fence_of(_payload(path))) + 1


def _stage(path: str, body: str) -> str:
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(body)
    return tmp


def heartbeat_lease(path: str, token: str, ttl_s: float = DEFAULT_TTL_S) -> dict[str, Any]:
    """Extend an owned, unexpired lease. Foreign/expired tokens refuse.

    The token re-check and the payload rewrite happen under the same
    lock, so a stale owner can neither extend after a takeover nor
    overwrite the new owner's payload (no stale-owner clobber).
    """
    if not str(token or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    try:
        ttl = float(ttl_s)
        if not (0 < ttl < 86400):
            return {"ok": False, "reason": "BAD_CONTRACT"}
    except (TypeError, ValueError):
        return {"ok": False, "reason": "BAD_CONTRACT"}
    with _holder_lock(path) as locked:
        if not locked:
            return {"ok": False, "reason": "LEASE_IO_ERROR"}
        current = _payload(path)
        if current is None:
            return {"ok": False, "reason": "LEASE_ABSENT"}
        if current.get("token") != token:
            return {"ok": False, "reason": "LEASE_NOT_OWNER"}
        if _expired(current, time.time()):
            return {"ok": False, "reason": "LEASE_EXPIRED"}
        now = time.time()
        current["expires_at"] = now + ttl
        staged = None
        try:
            staged = _stage(path, json.dumps(current))
            os.replace(staged, path)
        except OSError:
            if staged is not None:
                _remove_quietly(staged)
            return {"ok": False, "reason": "LEASE_IO_ERROR"}
    return {"ok": True}


def release_lease(path: str, token: str) -> dict[str, Any]:
    """Release an owned lease. Foreign tokens refuse without deleting.

    The token check and the unlink happen under the same lock, so a
    stale owner racing a takeover cannot delete the new owner's lease.
    """
    if not str(token or "").strip():
        return {"ok": False, "reason": "BAD_CONTRACT"}
    with _holder_lock(path) as locked:
        if not locked:
            return {"ok": False, "reason": "LEASE_IO_ERROR"}
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

    Acquires, re-verifies ownership immediately BEFORE fn (a loss between
    acquire and effect refuses without invoking fn — zero side effects),
    runs fn, then verifies AFTER: a takeover in between reports FENCED_OUT
    instead of blessing results produced without ownership. The lease is
    released afterward either way (best-effort). fn exceptions release the
    lease, then report FENCED_ACTION_FAILED — never a success. Callers must
    prepare before acquiring and keep fn to the bare effect with TTL well
    above effect duration; a TTL expiry mid-effect is detected after (the
    effect already ran) — use effect_with_lease for preparation/effect
    separation with a pre-effect gate.
    """
    acquired = acquire_lease(path, owner, ttl_s)
    if not acquired.get("ok"):
        return {"ok": False, "reason": acquired.get("reason", "LEASE_HELD"),
                "holder": acquired.get("holder")}
    pre = heartbeat_lease(path, acquired["token"], ttl_s)
    if not pre.get("ok"):
        release_lease(path, acquired["token"])
        return {"ok": False, "reason": "FENCED_OUT",
                "detail": "ownership lost before the critical section"}
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


def effect_with_lease(path: str, token: str, ttl_s: float, effect_fn: Any,
                      *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Invoke a broker effect only while lease ownership holds (S04).

    Preparation must happen BEFORE acquiring; pass the acquired token here.
    Verifies ownership immediately BEFORE effect_fn: a lost/expired/foreign
    token refuses FENCED_OUT without invoking the effect (zero broker
    placements). After the effect, re-verifies: a loss during refuses
    FENCED_OUT instead of blessing the result. Does NOT release the lease —
    the caller owns acquire/release around preparation/effect.
    """
    pre = heartbeat_lease(path, token, ttl_s)
    if not pre.get("ok"):
        return {"ok": False, "reason": "FENCED_OUT",
                "detail": "ownership lost before the effect; refusing "
                          "without placement"}
    try:
        result = effect_fn(*args, **kwargs)
    except Exception as exc:
        return {"ok": False, "reason": "FENCED_ACTION_FAILED",
                "detail": f"{type(exc).__name__}: {exc}"}
    post = heartbeat_lease(path, token, ttl_s)
    if not post.get("ok"):
        return {"ok": False, "reason": "FENCED_OUT",
                "detail": "ownership lost during the effect"}
    return {"ok": True, "result": result}
