"""
Databento provider — Open Interest via OPRA.PILLAR `statistics` schema (stat_type=9).
Uses tight pre-market window (10:00-13:30 UTC) where EOD OI is published — ~$0.15/ticker/day.
Heavy Mongo caching: 1 fetch per ticker per US trading date.

Circuit breaker (added 2026-07-21 v2.6): per-parent state machine silences the
~50-per-scan auth_account_locked WARN spam. Trips OPEN after CIRCUIT_MAX_FAILURES
consecutive upstream failures, holds OPEN for CIRCUIT_OPEN_TTL_SEC, then
half-opens on the next call (single probe). CLOSED on probe success, RE-OPENED
with incremented close_attempts on probe failure.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import os
import re
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls
from typing import Any

import databento as db

# Circuit-breaker observability: Prometheus gauge already exists (provider label).
# We import lazily inside the methods so tests that don't have observability.py on
# PYTHONPATH don't fail at module-load; if the gauge is missing, we silently no-op
# so the contractual behavior (skip upstream on OPEN, log state transitions) still
# works in environments where the metrics stack isn't wired.
try:
    from services.observability import circuit_breaker_state as _cb_gauge
except Exception:  # noqa: BLE001 — gauge is best-effort observability, not contract-critical
    _cb_gauge = None  # type: ignore[assignment]

log = logging.getLogger("databento")

DBN_KEY = os.environ.get("DATABENTO_API_KEY", "")
_hist_client: db.Historical | None = None

# --- Circuit breaker constants (overridable in tests via monkeypatch.setattr) ---
CIRCUIT_MAX_FAILURES = 3
CIRCUIT_OPEN_TTL_SEC = 600  # 10 minutes
# _neg_ttl_s (legacy negative-cache TTL) intentionally tracks CIRCUIT_OPEN_TTL_SEC
# at instance-init time so tests that monkeypatch the circuit TTL also narrow the
# negative-cache window. They live in the same 10-min window by design: the
# negative cache suppresses *legitimately-empty* successful fetches; the breaker
# suppresses upstream calls after *failed* fetches. If one ever drifts from the
# other, a stale _neg stamp could block the first half-open probe.


@dataclasses.dataclass
class _CircuitState:
    """Per-parent databento circuit breaker state.

    Transitions:
      CLOSED  → OPEN   on consecutive_failures >= CIRCUIT_MAX_FAILURES
      OPEN    → HALF-OPEN after CIRCUIT_OPEN_TTL_SEC elapses (next call probes)
      HALF-OPEN → CLOSED on probe success  (opened_at := None)
      HALF-OPEN → OPEN  on probe failure (close_attempts += 1, opened_at := now)
    """
    parent: str
    consecutive_failures: int = 0
    opened_at: datetime | None = None
    close_attempts: int = 0

    def is_open(self, now: datetime | None = None) -> bool:
        """True while the breaker is fully OPEN (TTL not elapsed) — caller must
        skip upstream. Returns False if CLOSED or in HALF-OPEN (TTL elapsed,
        awaiting a single probe)."""
        if self.opened_at is None:
            return False
        now = now or datetime.now(UTC)
        elapsed = (now - self.opened_at).total_seconds()
        return elapsed < CIRCUIT_OPEN_TTL_SEC


def _get_client() -> db.Historical | None:
    global _hist_client, DBN_KEY
    # Re-read env in case .env loaded after module import or key rotated
    key = os.environ.get("DATABENTO_API_KEY", "")
    if _hist_client is None or key != DBN_KEY:
        DBN_KEY = key
        _hist_client = db.Historical(key) if key else None
    return _hist_client


# Parent symbol mapping. SPX index options on CBOE = SPXW.OPT
PARENT_MAP = {
    "SPY": "SPY.OPT",
    "QQQ": "QQQ.OPT",
    "IWM": "IWM.OPT",
    "DIA": "DIA.OPT",
    "TLT": "TLT.OPT",
    "SPX": "SPXW.OPT",
    "^SPX": "SPXW.OPT",
    "SPXW": "SPXW.OPT",
    "AAPL": "AAPL.OPT",
    "NVDA": "NVDA.OPT",
    "TSLA": "TSLA.OPT",
    "META": "META.OPT",
    "AMZN": "AMZN.OPT",
    "MSFT": "MSFT.OPT",
    "GOOGL": "GOOGL.OPT",
    "AMD": "AMD.OPT",
    "AVGO": "AVGO.OPT",
    "NFLX": "NFLX.OPT",
    "COIN": "COIN.OPT",
    "PLTR": "PLTR.OPT",
    "MU": "MU.OPT",
}


OSI_RE = re.compile(r'^([A-Z]+)\s*(\d{2})(\d{2})(\d{2})([CP])(\d{8})$')


def parse_osi(raw: str) -> dict[str, Any] | None:
    """Parse OPRA OSI symbol like 'SPY   260612C00500000'"""
    m = OSI_RE.match(raw.strip())
    if not m:
        return None
    und, ymd, typ, strike = m.groups()
    return {
        "underlying": und,
        "expiry": f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}",
        "type": "call" if typ == "C" else "put",
        "strike": int(strike) / 1000.0,
    }


def _last_trading_day_utc(now: datetime | None = None) -> date_cls:
    """Approx US equities last trading day in UTC. Saturday/Sunday roll back.
    Uses America/New_York timezone for correct DST handling."""
    from zoneinfo import ZoneInfo
    ny_tz = ZoneInfo("America/New_York")
    n = (now or datetime.now(UTC)).astimezone(ny_tz)
    # After US market close (4pm ET)
    if n.hour >= 16:
        n = n.replace(hour=16, minute=0, second=0, microsecond=0)
    else:
        n = n.replace(hour=16, minute=0, second=0, microsecond=0) - timedelta(days=1)
    while n.weekday() >= 5:
        n -= timedelta(days=1)
    return n.date()


def _fetch_oi_sync(parent: str, day: date_cls) -> dict[str, Any]:
    """Blocking Databento fetch. Returns {raw_symbol: {strike, expiry, type, oi}}.
    Raises on SDK error (incl. auth_account_locked) so DatabentoCache.get can drive
    the circuit-breaker state machine and emit the per-parent OPEN/CLOSED transition
    log exactly once. Returns {} on successful-but-empty result."""
    client = _get_client()
    if not client:
        raise RuntimeError("databento client not initialized — missing DATABENTO_API_KEY")
    # Tight pre-market window where EOD OI is published
    start = f"{day.isoformat()}T10:00:00"
    end = f"{day.isoformat()}T13:30:00"
    data = client.timeseries.get_range(
        dataset="OPRA.PILLAR",
        symbols=[parent],
        stype_in="parent",
        schema="statistics",
        start=start,
        end=end,
        limit=300000,
    )
    df = data.to_df()

    if df is None or df.empty:
        return {}
    df = df[df["stat_type"] == 9]
    if df.empty:
        return {}
    # latest per symbol — sort by timestamp first to ensure .last() picks the newest
    df = df.sort_values("ts_event").groupby("symbol").last().reset_index()

    out: dict[str, dict[str, Any]] = {}
    for sym, qty in zip(df["symbol"], df["quantity"], strict=False):
        p = parse_osi(sym)
        if not p:
            continue
        if qty != qty or qty is None:  # NaN check first
            continue
        oi = int(qty)
        if oi <= 0:
            continue
        p["oi"] = oi
        out[sym] = p
    return out


class DatabentoCache:
    """Mongo-backed OI cache: doc per (parent, day) holds full snapshot.

    Per-parent circuit breaker prevents upstream spam when the databento
    account returns 403 auth_account_locked. State lives in self._circuit;
    accessor is_circuit_open() exposes the CLOSED-vs-OPEN bit for routes
    that want to surface it (currently /api/health optionally)."""

    def __init__(self, mongo_db: Any) -> None:
        self.col = mongo_db.databento_oi
        self._mem: dict[str, dict[str, Any]] = {}
        self._neg: dict[str, datetime] = {}   # key → time of last empty fetch
        # Bound at instance init so test monkeypatches of CIRCUIT_OPEN_TTL_SEC
        # narrow the negative-cache window in lockstep — keeps the two TTLs aligned.
        self._neg_ttl_s = CIRCUIT_OPEN_TTL_SEC
        self._circuit: dict[str, _CircuitState] = {}  # parent → circuit state

    async def ensure_index(self) -> None:
        with contextlib.suppress(Exception):
            await self.col.create_index([("parent", 1), ("day", 1)], unique=True)

    def is_circuit_open(self, parent: str) -> bool:
        """True while the breaker blocks upstream for this parent. False if the
        breaker is CLOSED or has elapsed into the HALF-OPEN probe window."""
        state = self._circuit.get(parent)
        return state.is_open() if state else False

    def snapshot_circuits(self) -> list[dict[str, Any]]:
        """Return a JSON-safe per-parent breaker snapshot for
        GET /api/databento/breaker/status. Sort order: OPENs first (by
        ttl_remaining_s ascending — closest-to-recovery on top), then
        HALF-OPEN, then CLOSED. Parents never seen by the engine are
        omitted (closed_count tracks those separately in the route).
        """
        out: list[dict[str, Any]] = []
        for parent, st in self._circuit.items():
            if st.opened_at is None:
                state = "closed"
                ttl_remaining = 0.0
                opened_iso = None
            elif st.is_open():
                state = "open"
                # Defense-in-depth clamp: `is_open()` already excludes the
                # negative-remaining case (it tests `< CIRCUIT_OPEN_TTL_SEC`),
                # but the `max(0.0, ...)` here guards against test-mock time
                # skew and the rare freeze-the-clock scenario. Without it, a
                # consumer reading `ttl_remaining_s` could see a negative
                # value mid-test and crash on `assert ttl_remaining >= 0`.
                ttl_remaining = max(
                    0.0,
                    CIRCUIT_OPEN_TTL_SEC - (datetime.now(UTC) - st.opened_at).total_seconds(),
                )
                opened_iso = st.opened_at.isoformat()
            else:
                # TTL elapsed but not yet probed — HALF-OPEN.
                state = "half_open"
                ttl_remaining = 0.0
                opened_iso = st.opened_at.isoformat()
            out.append(
                {
                    "parent": parent,
                    "state": state,
                    "consecutive_failures": st.consecutive_failures,
                    "close_attempts": st.close_attempts,
                    "opened_at": opened_iso,
                    "ttl_remaining_s": round(ttl_remaining, 1),
                }
            )
        # OPENs first by ttl_remaining ascending (closest to half-open probe on top),
        # then half_open, then closed by parent ascending for stable ordering.
        rank = {"open": 0, "half_open": 1, "closed": 2}
        out.sort(key=lambda r: (rank[r["state"]], r["ttl_remaining_s"] if r["state"] == "open" else 0, r["parent"]))
        return out

    def _on_failure(self, parent: str, err: Exception | None = None) -> None:
        """Record an upstream failure on the circuit. Promotes the breaker to OPEN
        when consecutive_failures crosses CIRCUIT_MAX_FAILURES; renews opened_at
        when a half-open probe fails. Emits ONE warn at the CLOSED→OPEN edge +
        propagates the SDK error message so on-the-floor trips stay diagnosable
        (we no longer emit per-call warns from `_fetch_oi_sync`). Subsequent
        OPEN-state calls are silent — the early-return short-circuits them."""
        state = self._circuit.setdefault(parent, _CircuitState(parent=parent))
        # Fast-path: if we're fully OPEN and TTL is still in window, nothing to do.
        # (Today unreachable because `get()` skips upstream at OPEN, but safe-by-default
        # against any future caller that invokes _on_failure directly.)
        if state.opened_at is not None and state.is_open():
            return
        state.consecutive_failures += 1
        if state.opened_at is None:
            if state.consecutive_failures >= CIRCUIT_MAX_FAILURES:
                state.opened_at = datetime.now(UTC)
                err_str = f"; last error: {err!r}" if err is not None else ""
                log.warning(
                    f"databento circuit OPENED — {parent} "
                    f"({state.consecutive_failures} consecutive failures; "
                    f"skip upstream for {CIRCUIT_OPEN_TTL_SEC}s{err_str})"
                )
                if _cb_gauge is not None:
                    with contextlib.suppress(Exception):
                        _cb_gauge.labels(provider="databento").set(1)
        elif not state.is_open():
            # HALF-OPEN phase: probe failed, re-open with bumped close_attempts.
            state.close_attempts += 1
            state.opened_at = datetime.now(UTC)
            log.debug(
                f"databento circuit REOPENED — {parent} "
                f"(half-open probe #{state.close_attempts} failed)"
            )
            if _cb_gauge is not None:
                with contextlib.suppress(Exception):
                    _cb_gauge.labels(provider="databento").set(1)

    def _on_success(self, parent: str) -> None:
        """Any upstream success (including empty-result) resets consecutive_failures
        and clears opened_at — the breaker closes. Symmetric short-circuit with
        `_on_failure`: if we're fully OPEN with TTL still in window, a stray call
        here would prematurely close the breaker before a probe is allowed AND
        silently zero the failure counter. The guard returns BEFORE both the
        counter reset and the opened_at clear, matching `_on_failure`'s
        return-BEFORE-increment placement. Today unreachable from `get()`,
        but the symmetry is intentional defense-in-depth."""
        state = self._circuit.get(parent)
        if state is None:
            return
        # Fast-path: fully OPEN with TTL still in window — leave state pristine.
        if state.opened_at is not None and state.is_open():
            return
        state.consecutive_failures = 0
        if state.opened_at is not None:
            prior_attempts = state.close_attempts
            state.opened_at = None
            state.close_attempts = 0
            log.info(
                f"databento circuit CLOSED — {parent} "
                f"(recovered after {prior_attempts} half-open probe(s))"
            )
            if _cb_gauge is not None:
                with contextlib.suppress(Exception):
                    _cb_gauge.labels(provider="databento").set(0)

    async def get(self, parent: str, day: date_cls) -> dict[str, Any]:
        key = f"{parent}:{day.isoformat()}"
        if key in self._mem:
            return self._mem[key]

        # Stale Mongo cache served regardless of circuit state — fetch_oi_for_ticker
        # backwalks across days and a breaker must not blind-side it.
        doc = await self.col.find_one({"parent": parent, "day": day.isoformat()}, {"_id": 0})
        if doc and doc.get("contracts"):
            contracts: dict[str, Any] = doc["contracts"]
            self._mem[key] = contracts
            return contracts

        # Negative cache: a recent empty fetch means "no data" — skip the
        # expensive re-fetch for a cooldown so repeated requests don't each
        # trigger the databento get_range calls that returned nothing.
        neg = self._neg.get(key)
        if neg is not None and (datetime.now(UTC) - neg).total_seconds() < self._neg_ttl_s:
            return {}

        # CIRCUIT BREAKER — OPEN state skips upstream silently. We deliberately
        # do NOT populate _mem so each call re-evaluates the breaker (this lets
        # the half-open probe fire after CIRCUIT_OPEN_TTL_SEC elapses).
        if self.is_circuit_open(parent):
            log.debug(f"databento: circuit OPEN — skipping upstream for {parent} {day}")
            return {}

        log.info(f"databento: fetching OI {parent} {day} (cache miss)")
        try:
            contracts = await asyncio.to_thread(_fetch_oi_sync, parent, day)
        except Exception:
            # Drive the breaker — count the failure but don't stamp _neg so a
            # half-open probe after TTL can still fire on the (parent, day) pair.
            self._on_failure(parent)
            return {}

        # Successful SDK round-trip counts as a probe success — reset/close breaker.
        self._on_success(parent)
        if not contracts:
            self._neg[key] = datetime.now(UTC)
            return {}
        self._neg.pop(key, None)   # got data — clear any negative mark
        await self.col.update_one(
            {"parent": parent, "day": day.isoformat()},
            {"$set": {"parent": parent, "day": day.isoformat(),
                      "contracts": contracts, "fetched_at": datetime.now(UTC).isoformat(),
                      "count": len(contracts)}},
            upsert=True,
        )
        self._mem[key] = contracts
        return contracts


_cache: DatabentoCache | None = None


def init_cache(mongo_db: Any) -> DatabentoCache:
    global _cache
    _cache = DatabentoCache(mongo_db)
    return _cache


def get_cache() -> DatabentoCache | None:
    return _cache


async def fetch_oi_for_ticker(ticker: str, day: date_cls | None = None) -> dict[str, Any]:
    """Public API: get OI keyed by raw OSI symbol for a ticker."""
    # 2026-09-02: Databento decommissioned for the flow stack (Public.com is
    # primary OI/chain source; cvserver is the fallback). The kill switch makes
    # the OFF switch explicit and testable instead of relying on key removal.
    if os.environ.get("DISABLE_DATABENTO", "").lower() in ("1", "true", "yes"):
        return {}
    key = os.environ.get("DATABENTO_API_KEY", DBN_KEY)
    if not key or not _cache:
        return {}
    parent = PARENT_MAP.get(ticker.upper().replace("^", ""))
    if not parent:
        parent = f"{ticker.upper().replace('^','')}.OPT"
    use_day = day or _last_trading_day_utc()
    # Walk back up to 4 trading days if data is missing
    for _ in range(4):
        contracts = await _cache.get(parent, use_day)
        if contracts:
            return contracts
        use_day -= timedelta(days=1)
        while use_day.weekday() >= 5:
            use_day -= timedelta(days=1)
    return {}


# ----------------------------- Live trades / Flowseeker -----------------------

async def stream_live_trades(parent: str, queue: asyncio.Queue[dict[str, Any]], stop_event: asyncio.Event, dry_run: bool = False) -> None:
    """Stream live OPRA trades for a parent symbol into a queue.
    EXPENSIVE — only run when client subscribes via /api/flow SSE.
    Hard-stops within ~2s of stop_event being set, even if no trades are flowing."""
    if dry_run:
        return
    key = os.environ.get("DATABENTO_API_KEY", DBN_KEY)
    if not key:
        loop = asyncio.get_event_loop()
        with contextlib.suppress(Exception):
            asyncio.run_coroutine_threadsafe(queue.put({"_error": "Databento key missing"}), loop)
        return
    loop = asyncio.get_event_loop()

    def _run() -> None:
        live = None
        try:
            live = db.Live(key=key)
            live.subscribe(
                dataset="OPRA.PILLAR",
                schema="trades",
                stype_in="parent",
                symbols=parent,
            )

            def cb(rec: Any) -> None:
                try:
                    if stop_event.is_set():
                        with contextlib.suppress(Exception):
                            live.stop()
                        return
                    sym = getattr(rec, "raw_symbol", None) or getattr(rec, "symbol", None)
                    if not sym:
                        return
                    parsed = parse_osi(sym) if sym else None
                    if not parsed:
                        return
                    px = getattr(rec, "price", 0) / 1e9 if hasattr(rec, "price") else 0
                    sz = getattr(rec, "size", 0)
                    ts = getattr(rec, "ts_event", 0)
                    side = getattr(rec, "side", None)
                    notional = px * sz * 100 if px and sz else 0
                    payload = {
                        "ts": ts,
                        "symbol": sym,
                        "underlying": parsed["underlying"],
                        "strike": parsed["strike"],
                        "expiry": parsed["expiry"],
                        "type": parsed["type"],
                        "price": px,
                        "size": sz,
                        "side": str(side) if side else None,
                        "notional": notional,
                        "unusual": sz >= 100 or notional >= 50000,
                        "sweep": sz >= 250,
                        "block": sz >= 500,
                    }
                    with contextlib.suppress(Exception):
                        asyncio.run_coroutine_threadsafe(queue.put(payload), loop)
                except Exception as e:
                    log.warning(f"flow cb err: {e}")

            live.add_callback(cb)
            live.start()

            # Poll stop_event every second so manual stop is responsive
            import time as _t
            t0 = _t.time()
            while _t.time() - t0 < 600:  # hard upper-bound 10 min safety
                if stop_event.is_set():
                    break
                _t.sleep(1)
        except Exception as e:
            log.warning(f"flow stream err: {e}")
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(queue.put({"_error": str(e)}), loop)
        finally:
            try:
                if live is not None:
                    live.stop()
            except Exception:
                pass

    await asyncio.to_thread(_run)
