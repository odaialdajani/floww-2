"""Universe scan scheduler: prefilter + batched builds + leaderboard.

Maximization build #2. Prefilter is pure/cheap (no options fetch);
batched builds debit the shared PublicBudget; leaderboard persists
to DuckDB universe_leaderboard_v1 (upsert, best-effort).
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)
SCHEMA_VERSION = "universe_scan.v1"
LEADERBOARD_TABLE_DDL = """
    CREATE TABLE IF NOT EXISTS universe_leaderboard_v1 (
        ticker VARCHAR, rank INTEGER, conviction DOUBLE,
        tier VARCHAR, direction VARCHAR, trade_type VARCHAR,
        invalidation VARCHAR, snapshot_id VARCHAR, asof_ts VARCHAR,
        evidence VARCHAR, updated_at VARCHAR
    )
"""
# Instruments with no listed options contract at all. These are excluded on
# fact, independent of which data path is used.
NON_OPTIONABLE = frozenset({"BTC", "ETH"})

# Index symbols whose options DO exist and are listed (VIX on Cboe, SPX on Cboe)
# but which this scanner's data path may not serve. That is an access/entitlement
# question, not a statement that the instrument is un-optionable, so conflating
# the two produced a factual error: ^SPX was reported NON_OPTIONABLE purely
# because one access path failed. Kept excluded by default so live behavior does
# not change, but reported under a distinct reason so the operator can tell
# "no options exist" from "we cannot see them".
ENTITLEMENT_UNVERIFIED = frozenset({"^VIX", "^SPX"})
SCAN_PACE_SEC = 6.0
MAX_TICKERS_PER_SWEEP = 20


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def prefilter_universe(universe=None, *, movers=None, prior=None, flow_alert_tickers=None, limit=MAX_TICKERS_PER_SWEEP):
    """Order universe for a sweep. PURE: no I/O, no Greeks.
    Score = |movers %| + prior_conviction/100 + 2.0 flow-alert bonus.
    Non-optionable excluded with reason; unknown kept (unknown!=bad).
    """
    from services.movers import POPULAR_UNIVERSE

    uni = list(universe) if universe else list(POPULAR_UNIVERSE)
    movers = movers or {}
    prior = prior or {}
    flow_alert_tickers = flow_alert_tickers or set()
    excluded = []
    ranked = []
    for t in uni:
        name = str(t or "").strip().upper()
        if not name:
            excluded.append({"ticker": name or str(t), "reason": "NON_OPTIONABLE"})
            continue
        if name in NON_OPTIONABLE:
            excluded.append({"ticker": name, "reason": "NON_OPTIONABLE"})
            continue
        if name in ENTITLEMENT_UNVERIFIED:
            # Options exist; this data path has not proven it can serve them.
            excluded.append({"ticker": name, "reason": "ENTITLEMENT_UNVERIFIED"})
            continue
        score = abs(float(movers.get(name, 0.0) or 0.0))
        score += float(prior.get(name, 0.0) or 0.0) / 100.0
        if name in flow_alert_tickers:
            score += 2.0
        ranked.append(
            {"ticker": name, "prefilter_score": round(score, 4), "has_flow_alert": name in flow_alert_tickers}
        )
    ranked.sort(key=lambda r: (-r["prefilter_score"], r["ticker"]))
    kept = ranked[: max(1, int(limit))]
    return {
        "schema_version": SCHEMA_VERSION,
        "ordered": kept,
        "excluded": excluded,
        "coverage": {"requested": len(uni), "kept": len(kept), "excluded": len(excluded)},
    }


def affordable_take(available, per_ticker, want):
    """How many tickers this sweep can afford. Pure (tested)."""
    try:
        per = max(1, int(per_ticker))
        avail = float(available or 0.0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(int(want), int(avail // per)))


async def scan_batch(
    tickers, *, build_heatmap_fn=None, opportunity_fn=None, conviction_fn=None, max_expiries=2, pace_sec=SCAN_PACE_SEC
):
    """Build heatmaps+opportunity+conviction for one prefiltered batch.
    Peeks shared PublicBudget before EACH ticker; stops (keeping prior
    rows) when next build unaffordable. Injected fns = unit-testable.
    """
    from services.public_budget import budget as _pub_budget

    try:
        from services.public_scanner import chain_cost as _chain_cost

        per_ticker = _chain_cost(max_expiries)
    except Exception:
        per_ticker = 2 + max(0, int(max_expiries))
    if build_heatmap_fn is None:
        from server import build_heatmap as _build

        build_heatmap_fn = _build
    rows = []
    skipped = []
    scanned = 0
    for t in tickers or []:
        try:
            available = await _pub_budget.peek_available()
        except Exception:
            available = float("inf")
        if available < per_ticker:
            skipped.append({"ticker": t, "reason": "BUDGET_UNAFFORDABLE"})
            continue
        try:
            heat = await build_heatmap_fn(t, max_expiries=max_expiries)
        except Exception as e:
            skipped.append({"ticker": t, "reason": f"HEATMAP_FAIL: {e}"})
            continue
        scanned += 1
        row = {
            "ticker": str(t).upper(),
            "snapshot_id": (heat or {}).get("snapshotId"),
            "spot": (heat or {}).get("spot"),
            "asof": (heat or {}).get("asof"),
            "status": "ok",
        }
        if opportunity_fn is not None:
            try:
                row["opportunity"] = opportunity_fn(t, heat)
            except Exception as e:
                row["opportunity"] = {"error": str(e)}
        if conviction_fn is not None:
            try:
                row["conviction"] = conviction_fn(t, heat, row.get("opportunity"))
            except Exception as e:
                row["conviction"] = {"error": str(e)}
        rows.append(row)
        if pace_sec and scanned < len(tickers or []):
            try:
                import asyncio as _aio

                await _aio.sleep(max(0.0, float(pace_sec)))
            except Exception:
                pass  # silent by design: inter-ticker pacing sleep; a failed sleep must not abort the scan
    return {
        "schema_version": SCHEMA_VERSION,
        "rows": rows,
        "skipped": skipped,
        "coverage": {"requested": len(tickers or []), "scanned": scanned, "skipped": len(skipped)},
        "computed_at": _now_iso(),
    }


def record_leaderboard(conn, rows):
    """Upsert leaderboard rows (one per ticker). Best-effort, never raises."""
    try:
        from services.heatmap_history import _RECORDER_LOCK, _esc, ensure_tables

        ensure_tables(conn)
        try:
            conn.execute(LEADERBOARD_TABLE_DDL)
        except Exception as e:
            log.warning("leaderboard ensure failed: %s", e)
        with _RECORDER_LOCK:
            for r in rows or []:
                try:
                    conn.execute("DELETE FROM universe_leaderboard_v1 WHERE ticker = " + _esc(r.get("ticker")))
                    conn.execute(
                        "INSERT INTO universe_leaderboard_v1 VALUES ("
                        + ",".join(
                            [
                                _esc(r.get("ticker")),
                                _esc(r.get("rank")),
                                _esc(r.get("conviction")),
                                _esc(r.get("tier")),
                                _esc(r.get("direction")),
                                _esc(r.get("trade_type")),
                                _esc(r.get("invalidation")),
                                _esc(r.get("snapshot_id")),
                                _esc(r.get("asof")),
                                _esc(json.dumps(r.get("evidence") or {}, default=str)),
                                _esc(_now_iso()),
                            ]
                        )
                        + ")"
                    )
                except Exception as e:
                    log.warning("leaderboard record failed for %s: %s", r.get("ticker"), e)
    except Exception as e:
        log.warning("leaderboard record failed: %s", e)


def latest_leaderboard(conn, limit=50):
    """Load ranked leaderboard view. Empty when never scanned."""
    try:
        from services.heatmap_history import ensure_tables

        ensure_tables(conn)
        with contextlib.suppress(Exception):
            conn.execute(LEADERBOARD_TABLE_DDL)
        rows = conn.execute(
            "SELECT ticker, rank, conviction, tier, direction, trade_type,"
            + " invalidation, snapshot_id, asof_ts, evidence, updated_at"
            + " FROM universe_leaderboard_v1 ORDER BY rank ASC LIMIT "
            + str(max(1, int(limit)))
        ).fetchall()
        out = []
        for r in rows or []:
            try:
                ev = json.loads(r[9]) if isinstance(r[9], str) else (r[9] or {})
            except Exception:
                ev = {}
            out.append(
                {
                    "ticker": r[0],
                    "rank": r[1],
                    "conviction": r[2],
                    "tier": r[3],
                    "direction": r[4],
                    "trade_type": r[5],
                    "invalidation": r[6],
                    "snapshot_id": r[7],
                    "asof": r[8],
                    "evidence": ev if isinstance(ev, dict) else {},
                    "updated_at": r[10],
                }
            )
        return out
    except Exception as e:
        log.debug("latest_leaderboard failed: %s", e)
        return []


def leaderboard_age_s(conn):
    """Seconds since leaderboard last written. None when never."""
    try:
        from services.heatmap_history import ensure_tables

        ensure_tables(conn)
        with contextlib.suppress(Exception):
            conn.execute(LEADERBOARD_TABLE_DDL)
        rows = conn.execute("SELECT MAX(updated_at) FROM universe_leaderboard_v1").fetchall()
        if not rows or not rows[0][0]:
            return None
        try:
            from datetime import datetime as _dt

            ts = _dt.fromisoformat(str(rows[0][0]))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            return max(0.0, (_dt.now(UTC) - ts).total_seconds())
        except Exception:
            return None
    except Exception:
        return None


__all__ = [
    "prefilter_universe",
    "affordable_take",
    "scan_batch",
    "record_leaderboard",
    "latest_leaderboard",
    "leaderboard_age_s",
    "SCHEMA_VERSION",
    "SCAN_PACE_SEC",
    "MAX_TICKERS_PER_SWEEP",
    "NON_OPTIONABLE",
]
