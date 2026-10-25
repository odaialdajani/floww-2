"""Read-only historical price/node chart. Never feeds replay into live data."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from services.price_node_history import build_history, epoch

router = APIRouter(prefix="/api/heatseeker", tags=["price-node-history"])

# Only overlapping, identical market-data reads share work. Completed results
# are never cached or stale-served; each caller still joins its own node scope.
_bar_reads: dict[tuple, asyncio.Task] = {}
# One clock for admission, broker lock/init, pacing and bars, including orphaned
# jobs. Leave headroom below the browser's 30s request timeout.
_HISTORY_JOB_TIMEOUT_SECONDS = 20.0


async def _history_bars(ticker, period, aggregation, sessions, instrument_type="EQUITY"):
    from services.public_api_adapter import fetch_bars_by_interval
    from services.public_budget import BudgetExhausted, budget, wait_for_read_admission

    key = (asyncio.get_running_loop(), ticker, period, aggregation, sessions, instrument_type)
    task = _bar_reads.get(key)
    if task is None or task.done():
        async def fetch():
            try:
                async with asyncio.timeout(_HISTORY_JOB_TIMEOUT_SECONDS):
                    try:
                        await wait_for_read_admission(lambda: budget.acquire("api.public.com"))
                    except BudgetExhausted as exc:
                        return [], {"reason": exc.reason, "retry_after_seconds": exc.retry_after}, None
                    except Exception:
                        return [], {"reason": "budget_unavailable", "retry_after_seconds": None}, None
                    try:
                        kwargs = {"period": period, "aggregation": aggregation, "sessions": sessions}
                        if instrument_type != "EQUITY":
                            kwargs["instrument_type"] = instrument_type
                        bars = await fetch_bars_by_interval(ticker, **kwargs)
                        if not bars:
                            return [], {"reason": "provider_unavailable", "retry_after_seconds": None}, None
                        return bars, None, datetime.now(UTC).isoformat()
                    except Exception:
                        return [], {"reason": "provider_unavailable", "retry_after_seconds": None}, None
                    finally:
                        budget.release()
            except TimeoutError:
                return [], {"reason": "history_job_timeout", "retry_after_seconds": None}, None

        task = asyncio.create_task(fetch())
        _bar_reads[key] = task

        def finished(done):
            if _bar_reads.get(key) is done:
                _bar_reads.pop(key, None)
            if not done.cancelled():
                done.exception()  # retrieve even if every waiting browser closed

        task.add_done_callback(finished)
    # A cancelled waiter cannot cancel shared work or release its budget slot.
    return await asyncio.shield(task)


def read_snapshots(engine, ticker, first, last):
    base = ("SELECT snapshot_id, ticker, query_key, expiries, formula_version, exposure_basis, asof_ts, received_at, walls_json%s "
            "FROM heatmap_snapshots_v2 WHERE ticker = ? "
            "AND TRY_CAST(asof_ts AS TIMESTAMPTZ) >= ? "
            "AND TRY_CAST(asof_ts AS TIMESTAMPTZ) <= ? "
            "ORDER BY TRY_CAST(asof_ts AS TIMESTAMPTZ), snapshot_id LIMIT 50001")
    try:
        return engine.query_strict(base % ", strikes_json", [ticker, first, last])
    except Exception:
        # Older stores predate the strikes_json column: legacy read keeps
        # nodes working, exposure centres simply stay null.
        return engine.query_strict(base % "", [ticker, first, last])


def recording_summary(engine, ticker):
    """Actual backing and saved range, including records newer than the candles."""
    from services.connection_guard import connection_lock
    from services.heatmap_history import recorder_status

    with connection_lock(engine.conn):
        status = recorder_status(engine.conn)
    rows = engine.query_strict(
        "SELECT MIN(TRY_CAST(asof_ts AS TIMESTAMPTZ)) AS first_at, "
        "MAX(TRY_CAST(asof_ts AS TIMESTAMPTZ)) AS last_at, COUNT(*) AS count "
        "FROM heatmap_snapshots_v2 WHERE ticker = ?", [ticker],
    )
    saved = rows[0] if rows else {}
    return {"durable": status["durable"], "status": "available",
            "first_at": saved.get("first_at"), "last_at": saved.get("last_at"),
            "count": saved.get("count", 0)}


@router.post("/record/{ticker}")
async def record_snapshot_now(ticker: str, expiries: int = Query(4, ge=1, le=12),
                              mode: str = Query("day", pattern="^(day|swing|scalp)$"),
                              dte: int | None = Query(None, ge=0, le=30),
                              scalp: bool = Query(False)):
    """Record-now: fresh heatmap build for one symbol, awaited into the store.

    User-initiated explicit spend (same cost as a manual desk refresh). Returns
    the recorded snapshot identity; 429 when the provider budget is exhausted,
    503 when the row never lands within the bound (never a fabricated row).
    """
    from server import _build_heatmap_impl
    from services.duckdb_engine import db
    from services.heatmap_history import observation_id_for, replay_snapshot
    from services.public_budget import BudgetExhausted
    from services.solstice_scope import cache_key as scope_cache_key
    from services.solstice_scope import request_query

    t = ticker.strip().upper()
    if not t or len(t) > 12:
        raise HTTPException(status_code=422, detail="Choose a valid ticker symbol")
    try:
        payload = await _build_heatmap_impl(t, expiries, True, mode, dte, scalp)
    except BudgetExhausted as err:
        raise HTTPException(status_code=429, detail="Provider budget exhausted; retry after cooldown") from err
    if not isinstance(payload, dict) or payload.get("error"):
        raise HTTPException(status_code=503, detail="Fresh build failed; nothing recorded")
    try:
        scope = scope_cache_key(t, request_query(expiries, mode, dte, scalp, True, 200))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        sid = observation_id_for(payload)
    except Exception as err:
        raise HTTPException(status_code=503, detail="Observation identity failed; nothing recorded") from err
    conn = getattr(db, "conn", None)
    for _ in range(20):
        try:
            found = replay_snapshot(conn, sid) if conn is not None else None
        except Exception:
            found = None
        if found:
            return {"snapshot_id": sid, "ticker": t, "asof": payload.get("asof"), "scope": scope}
        await asyncio.sleep(1)
    raise HTTPException(status_code=503, detail="Recording did not land within 20s; retry or check recorder status")


def _recorded_envelopes(ticker, bars, receipt, bar_seconds, opening_minutes,
                        tick_size, units, entitlement, max_delay_seconds):
    """R21-03/04 supplier half: admission envelopes alongside THIS read's own
    bars. The master truth is the committed admission modules; every envelope
    is computed from rows knowable at an explicit cursor — the read's own
    recorded receipt when present, else the newest bar's own clock. Sources
    this route does not carry are NAMED in the exact refused/unavailable
    vocabulary instead of becoming invented totals."""
    from services.chart_darkpool import admit_darkpool_prints
    from services.chart_delta import admit_delta
    from services.chart_flow import admit_flow_bucket, resolve_epoch, session_bounds_for_date
    from services.chart_profiles import admit_initial_balance
    valid_clock_bars = [bar for bar in bars if isinstance(bar, dict) and epoch(bar.get("t")) is not None]
    malformed_clocks = len(bars) - len(valid_clock_bars)
    normalized = build_history(ticker, valid_clock_bars, [], bar_seconds=bar_seconds)["frames"]
    bars = [{"t": frame["time"], "o": frame["open"], "h": frame["high"],
             "l": frame["low"], "c": frame["close"]} for frame in normalized]
    source_gaps = {"malformed_bar_clock": malformed_clocks,
                   "invalid_or_duplicate_bars": len(valid_clock_bars) - len(bars)}
    if not bars:
        missing = {"status": "unavailable", "reason": "no valid bar clocks at this supplier"}
        return {"session": None, "source_gaps": source_gaps,
                **{key: dict(missing) for key in ("initial_balance", "flow", "naked", "delta", "darkpool")}}
    # The response rides the newest catalogued session of this read.
    read_dates = sorted({datetime.fromtimestamp(epoch(bar.get("t")), UTC).astimezone(ZoneInfo("America/New_York")).date()
                         for bar in bars if bar.get("t") is not None})
    last_date = read_dates[-1]
    upright = ticker.strip().upper()
    knowable = [epoch(bar.get("t")) for bar in bars if bar.get("t") is not None]
    receipt_epoch = resolve_epoch(receipt)
    cursor = receipt_epoch if isinstance(receipt_epoch, (int, float)) else (max(knowable) if knowable else None)
    session_block = {"date": last_date.isoformat(), "tz": "America/New_York"}
    live_date = None
    if isinstance(receipt_epoch, (int, float)):
        live_date = datetime.fromtimestamp(receipt_epoch, UTC).astimezone(ZoneInfo("America/New_York")).date()
    bounds = session_bounds_for_date(last_date)
    if bounds:
        session_block.update({"start": bounds["start"], "end": bounds["end"]})
    # The contract ties an autonomous admission to the cursor's own session.
    # A fresh provider read has no per-bar recorded receipts, so only the
    # receipt's own live day can carry receipt clocks; any older day in the
    # range honestly gets no envelope from this supplier.
    live_session = live_date is not None and live_date in read_dates
    if live_session:
        ib_rows = [{"time": epoch(bar.get("t")), "open": bar.get("o"), "high": bar.get("h"),
                    "low": bar.get("l"), "close": bar.get("c"), "received_at": receipt_epoch}
                   for bar in bars
                   if bar.get("t") is not None
                   and datetime.fromtimestamp(epoch(bar.get("t")), UTC).astimezone(ZoneInfo("America/New_York")).date() == live_date]
        ib_envelope = admit_initial_balance(
            ib_rows, ticker=upright, cursor=cursor, bar_seconds=bar_seconds,
            session_date=live_date.isoformat(), opening_minutes=opening_minutes,
            tick_size=tick_size, units=units, entitlement=entitlement)
    else:
        ib_envelope = {"status": "not_requested",
                       "reason": "no live-session bars for the receipt's own day; the supplier does not fabricate availability for older days"}
    return {
        "source_gaps": source_gaps,
        "session": session_block,
        "initial_balance": ib_envelope,
        "flow": admit_flow_bucket([], ticker=upright, cursor=cursor, bar_seconds=bar_seconds),
        "naked": {"status": "not_requested",
                  "reason": "no naked-level candidates at this supplier; claims render only when explicit candidates and coverage exist"},
        # No classified-size source rides this read, so the capability stays
        # undeclared: the contract's own refusal names the gap exactly.
        "delta": admit_delta(
            [], ticker=upright, cursor=cursor, bar_seconds=bar_seconds,
            capabilities={}, tick_size=tick_size, units=units,
            entitlement=entitlement),
        "darkpool": admit_darkpool_prints(
            [], ticker=upright, cursor=cursor, bar_seconds=bar_seconds,
            tick_size=tick_size, units=units, entitlement=entitlement,
            max_delay_seconds=max_delay_seconds),
    }


@router.get("/price-history/{ticker}")
async def price_history(ticker: str, days: int = Query(5, ge=1, le=2600),
                        query_key: str | None = Query(None, max_length=2000),
                        interval_minutes: int | None = Query(None, ge=1, le=60),
                        include_metric_lines: bool = Query(False),
                        contract_symbol: str | None = Query(None, max_length=32),
                        sessions: str = Query("regular", pattern="^(regular|all)$"),
                        include_envelopes: bool = False,
                        opening_minutes: int = 60,
                        tick_size: float = 0.01,
                        units: str = "usd",
                        entitlement: str = "delayed-15m",
                        max_delay_seconds: int = 900):
    if interval_minutes is not None and interval_minutes not in {1, 5, 15, 30, 60}:
        raise HTTPException(status_code=422, detail="Choose 1, 5, 15, 30 or 60 minute candles")
    contract = None
    if contract_symbol is not None:
        contract = contract_symbol.strip().upper()
        if not contract or len(contract) > 32 or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789." for ch in contract):
            raise HTTPException(status_code=422, detail="Choose a valid option contract symbol (OSI)")
    from services.duckdb_engine import db
    ticker = ticker.strip().upper()
    try:
        recording = await asyncio.to_thread(recording_summary, db, ticker)
    except Exception:
        recording = {"status": "unavailable", "durable": False}
    # Period brackets: Public.com's historicdata gateway rejects TEN_YEARS
    # (400) and serves at most FIVE_YEARS (~1255 daily bars) — verified live
    # 2026-10-11. The 10-year UI option therefore requests FIVE_YEARS, the
    # provider's real maximum; never a label Public 400s on.
    period, aggregation, bar_seconds = ("DAY", "ONE_MINUTE", 60) if days == 1 else ("WEEK", "FIVE_MINUTES", 300) if days <= 5 else ("MONTH", "ONE_HOUR", 3600) if days <= 20 else ("QUARTER", "ONE_DAY", 86400) if days <= 60 else ("YEAR", "ONE_DAY", 86400) if days <= 260 else ("FIVE_YEARS", "ONE_DAY", 86400)
    if interval_minutes is not None:
        aggregation = {1: "ONE_MINUTE", 5: "FIVE_MINUTES", 15: "FIFTEEN_MINUTES",
                       30: "THIRTY_MINUTES", 60: "ONE_HOUR"}[interval_minutes]
        bar_seconds = interval_minutes * 60
    # This path deliberately does not use market_bars' stale-on-error cache:
    # a failed historical fetch must be visible, not labelled as a new read.
    bars, price_failure, received_at = await _history_bars(ticker, period, aggregation, sessions)
    price_only = build_history(ticker, bars, [], query_key, bar_seconds)
    session_dates = sorted({datetime.fromtimestamp(epoch(frame["time"]), UTC).astimezone(ZoneInfo("America/New_York")).date()
                            for frame in price_only["frames"]})
    if interval_minutes is not None and len(session_dates) > days:
        keep = set(session_dates[-days:])
        valid_instants = {epoch(frame["time"]) for frame in price_only["frames"]
                          if datetime.fromtimestamp(epoch(frame["time"]), UTC).astimezone(ZoneInfo("America/New_York")).date() in keep}
        bars = [bar for bar in bars if epoch(bar.get("t")) in valid_instants]
        price_only = build_history(ticker, bars, [], query_key, bar_seconds)
        session_dates = session_dates[-days:]
    valid_times = [epoch(frame["time"]) for frame in price_only["frames"]]
    if not valid_times:
        return {**build_history(ticker, [], [], query_key, bar_seconds), "price_status": "unavailable",
                "node_status": "not_loaded", "days": days, "recording": recording,
                "price_failure": price_failure or {"reason": "invalid_price_bars", "retry_after_seconds": None},
                "prices_received_at": received_at,
                "contract_symbol": contract,
                "contract_status": "unavailable" if contract is not None else "not_requested",
                "contract_bars": []}
    first = datetime.fromtimestamp(min(valid_times), UTC) - timedelta(minutes=15)
    last = datetime.fromtimestamp(max(valid_times), UTC)
    node_status = "available"
    try:
        rows = await asyncio.to_thread(read_snapshots, db, ticker, first, last)
    except Exception:
        rows = []
        node_status = "unavailable"
    truncated = len(rows) > 50000
    if truncated:
        rows = rows[:50000]
    result = build_history(ticker, bars, rows, query_key, bar_seconds)
    if node_status == "unavailable":
        result["node_coverage"] = {"scope_status": "unavailable", "gap_counts": None}
    if include_metric_lines:
        from services.recorded_price_levels import enrich_recorded_levels
        result = await asyncio.to_thread(enrich_recorded_levels, result, db)
    for frame in result["frames"]:
        frame["duration_seconds"] = bar_seconds
    # M3 contract premium path: the selected option contract's own OHLCV
    # (Public OSI bars, market-data key only). Own dollars, own axis — never
    # mixed into the underlying candles. Missing stays explicitly unavailable.
    contract_bars: list = []
    contract_status = "not_requested"
    if contract is not None:
        contract_status = "unavailable"
        fetched, _, _ = await _history_bars(contract, period, aggregation, sessions, "OPTION")
        contract_bars = fetched if isinstance(fetched, list) else []
        if contract_bars:
            contract_status = "available"
    result = {**result, "price_status": "available", "price_failure": None, "node_status": node_status,
            "records_truncated": truncated, "days": days, "prices_received_at": received_at,
            "last_candle_at": datetime.fromtimestamp(max(valid_times), UTC).isoformat(),
            "bar_seconds": bar_seconds, "price_sessions_returned": len(session_dates), "recording": recording,
            "contract_symbol": contract, "contract_status": contract_status,
            "contract_bars": contract_bars}
    if include_envelopes and bars:
        result["envelopes"] = _recorded_envelopes(
            ticker, bars, received_at, bar_seconds, opening_minutes,
            tick_size, units, entitlement, max_delay_seconds)
    return result


@router.get("/mapped-levels/{target}")
async def mapped_levels(
    target: str,
    source: str = Query(..., min_length=1, max_length=12),
    cursor: float = Query(...),
    combine: str | None = Query(None, max_length=32),
    scope: str | None = Query(None, max_length=64),
):
    """B09 cross-instrument mapped levels: the ratio lock + typed refusals only.

    Contract: C2-PRODUCER-CONTRACTS-20261024.json v2 b09_mapped_levels_contract.
    Supported pairs only (C040); the review-mode ratio is an explicit
    horizontal lock at-or-before the cursor (C042); C115 board-combination
    stays a refusal; levels are never invented (levels_status says so).
    """
    from services.chart_mapped_levels import is_supported_pair, mapped_levels_response

    target = target.strip().upper()
    source = source.strip().upper()
    combine_clean = (combine or "").strip().lower() or None
    scope_clean = (scope or "").strip().upper() or None

    # Pair validation BEFORE any provider read: an unsupported pair never spends one.
    if not is_supported_pair(source, target):
        return mapped_levels_response(target, source, cursor, [], [], combine_clean)

    src_bars, _, _ = await _history_bars(source, "DAY", "FIVE_MINUTES", "regular")
    tgt_bars, _, _ = await _history_bars(target, "DAY", "FIVE_MINUTES", "regular")
    body = mapped_levels_response(target, source, cursor,
                                   src_bars or [], tgt_bars or [], combine_clean)
    if scope_clean:
        body["scope"] = scope_clean
    return body
