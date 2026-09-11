"""
backend/services/journal_store.py

Server-side persistence for auto-seeded trade-journal entries — the backend
half of the Flowseeker signal-to-trade pipeline. Seeds are written to DuckDB
at execute-time so they survive browser localStorage clears and sync across
devices. The frontend keeps its floww_trades_v2 localStorage store as the
offline cache and merges server rows on load (server wins on conflicts by
updated_at).

Schema mirrors the frontend's floww_trades_v2 entry shape exactly
(ticker, type, action, strike, expiry, quantity, entry_price, exit_price,
entry_date, exit_date, notes, gex_regime, setup, tags) plus provenance:
ckey (alert contract key), source, created_at, updated_at.

Dedupe key = ticker|type|action|strike|expiry|entry_date — identical to
frontend/src/components/flowseeker/autoTrade.js journalSeedKey().
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Dedicated FILE-BACKED store. The shared duckdb_engine.db is :memory:
# (rebuilt each process start) — fine for scan-derived data, wrong for a
# trade journal, which must survive restarts. Same file-per-concern pattern
# as graph_trade_service.research_kg.duckdb.
_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "journal.duckdb"
_engine = None
_lock = threading.Lock()


def get_engine():
    """Lazily-created singleton DuckDBEngine at data/journal.duckdb."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from services.duckdb_engine import DuckDBEngine
                _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                _engine = DuckDBEngine(str(_DB_PATH))
                logger.info("Journal store opened at %s", _DB_PATH)
    return _engine

_JOURNAL_DDL = """
    CREATE TABLE IF NOT EXISTS flow_journal_trades (
        ckey TEXT,
        ticker TEXT NOT NULL,
        type TEXT,
        action TEXT,
        strike DOUBLE,
        expiry TEXT,
        quantity TEXT,
        entry_price DOUBLE,
        exit_price DOUBLE,
        entry_date TEXT,
        exit_date TEXT,
        notes TEXT,
        gex_regime TEXT,
        setup TEXT,
        tags TEXT,
        key_levels_json TEXT,
        source TEXT DEFAULT 'flowseeker-auto',
        created_at TIMESTAMP DEFAULT current_timestamp,
        updated_at TIMESTAMP DEFAULT current_timestamp,
        PRIMARY KEY (ticker, type, action, strike, expiry, entry_date)
    )
"""


def init_journal_tables(engine) -> None:
    """Create the journal table if absent; migrate older shapes in place."""
    engine.execute_write(_JOURNAL_DDL)
    with contextlib.suppress(Exception):
        engine.execute_write(
            "ALTER TABLE flow_journal_trades ADD COLUMN IF NOT EXISTS key_levels_json TEXT")


def journal_seed_key(seed: dict) -> str:
    """Same composite key as the frontend's journalSeedKey()."""
    return "|".join(str(seed.get(k) or "") for k in
                    ("ticker", "type", "action", "strike", "expiry", "entry_date"))


def _to_db_row(seed: dict) -> dict[str, Any]:
    """floww_trades_v2-shaped seed → column map. Numeric coercion is
    defensive: alerts always carry numeric strike/est_entry but a corrupted
    payload must not 500 the execute route."""
    def _num(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return {
        "ckey": seed.get("ckey"),
        "ticker": str(seed.get("ticker") or "").upper(),
        "type": str(seed.get("type") or "call").lower(),
        "action": str(seed.get("action") or "buy").lower(),
        "strike": _num(seed.get("strike")),
        "expiry": str(seed.get("expiry") or ""),
        "quantity": str(seed.get("quantity") or "1"),
        "entry_price": _num(seed.get("entry_price")),
        "exit_price": _num(seed.get("exit_price")) if seed.get("exit_price") not in ("", None) else None,
        "entry_date": str(seed.get("entry_date") or ""),
        "exit_date": str(seed.get("exit_date") or ""),
        "notes": str(seed.get("notes") or ""),
        "gex_regime": str(seed.get("gex_regime") or ""),
        "setup": str(seed.get("setup") or ""),
        "tags": str(seed.get("tags") or ""),
        "source": str(seed.get("source") or "flowseeker-auto"),
        "key_levels_json": json.dumps(seed["key_levels"]) if seed.get("key_levels") else None,
    }


def save_seeds(engine, seeds: list[dict]) -> int:
    """Insert seeds, skipping contracts already journaled. Returns count added."""
    added = 0
    for seed in seeds or []:
        row = _to_db_row(seed)
        if not row["ticker"]:
            continue
        try:
            engine.execute_write(
                """
                INSERT INTO flow_journal_trades (
                    ckey, ticker, type, action, strike, expiry, quantity,
                    entry_price, exit_price, entry_date, exit_date, notes,
                    gex_regime, setup, tags, source, key_levels_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [[row["ckey"], row["ticker"], row["type"], row["action"],
                 row["strike"], row["expiry"], row["quantity"],
                 row["entry_price"], row["exit_price"], row["entry_date"],
                 row["exit_date"], row["notes"], row["gex_regime"],
                 row["setup"], row["tags"], row["source"],
                 row["key_levels_json"]]],
            )
            added += 1
        except Exception as e:
            # PK conflict = already journaled (expected on re-execute);
            # anything else gets logged but never breaks the trade path.
            if "Constraint" not in type(e).__name__ and "constraint" not in str(e).lower():
                logger.warning("journal seed insert failed for %s: %s",
                               journal_seed_key(row), e)
    return added


_COLS = ("ckey, ticker, type, action, strike, expiry, quantity, entry_price, "
         "exit_price, entry_date, exit_date, notes, gex_regime, setup, tags, "
         "source, key_levels_json, created_at, updated_at")


def read_trades(engine, *, status: str = "all", days: int = 365) -> list[dict]:
    """Read journal rows as floww_trades_v2-shaped dicts (+ provenance).
    status: all | open | closed. Closed = has exit_date OR any exit price."""
    cutoff = f"current_timestamp - INTERVAL '{int(days)}' DAY"
    where = ""
    if status == "open":
        where = (f"WHERE COALESCE(exit_date, '') = '' AND exit_price IS NULL "
                 f"AND created_at > {cutoff}")
    elif status == "closed":
        where = "WHERE NOT (COALESCE(exit_date, '') = '' AND exit_price IS NULL)"
    rows = engine.query(
        f"SELECT {_COLS} FROM flow_journal_trades {where} "
        f"ORDER BY created_at DESC LIMIT 2000"
    )
    out: list[dict] = []
    for r in rows:
        out.append({
            **{k: r.get(k) for k in
               ("ticker", "type", "action", "expiry", "quantity", "notes",
                "gex_regime", "setup", "tags", "ckey", "source")},
            "strike": r.get("strike"),
            "entry_price": r.get("entry_price"),
            # frontend treats "" as no-exit
            "exit_price": r["exit_price"] if r.get("exit_price") is not None else "",
            "exit_date": r.get("exit_date") or "",
            "entry_date": r.get("entry_date") or "",
            "key_levels": (json.loads(r["key_levels_json"])
                           if r.get("key_levels_json") else None),
            "created_at": str(r.get("created_at") or ""),
            "updated_at": str(r.get("updated_at") or ""),
        })
    return out


def close_open_by_symbol(engine, symbol: str, *, exit_price: float,
                         exit_date: str) -> int:
    """Close ALL open journal cards for a symbol (first close wins on
    already-closed cards). Returns count closed. Used by the paper-engine
    close-out hook: when a position nets to flat, every auto-seeded card
    for that symbol gets its exit stamped automatically."""
    try:
        rows = engine.query(
            "SELECT ticker, type, action, strike, expiry, entry_date "
            "FROM flow_journal_trades "
            "WHERE ticker = ? AND COALESCE(exit_date, '') = '' AND exit_price IS NULL",
            [str(symbol).upper()],
        )
        closed = 0
        for r in rows:
            key = "|".join(str(r.get(k) or "") for k in
                           ("ticker", "type", "action", "strike", "expiry", "entry_date"))
            if close_trade(engine, key, exit_price=exit_price, exit_date=exit_date):
                closed += 1
        return closed
    except Exception as e:
        logger.warning("close_open_by_symbol failed for %s: %s", symbol, e)
        return 0


def journal_lifecycle(engine, spot_map: dict) -> int:
    """Blademap v3 lifecycle pass — close open journal cards against their
    own key levels using the freshest per-scan spots (same stamps that feed
    update_moves):

      BULLISH card: spot <= invalidation → stop out; spot >= target → win
      BEARISH card: mirrored

    Exit price is the LEVEL, not the scan spot (the level is the falsifiable
    claim; fills at/through it are execution detail). Cards without stored
    key_levels are never touched. Returns count closed; never raises into
    the scan loop.

    Bias source: the card's type field — call = bullish, put = bearish
    (the bridge only seeds BUY-side directional cards).
    """
    try:
        rows = engine.query(
            "SELECT ticker, type, action, strike, expiry, entry_date, key_levels_json "
            "FROM flow_journal_trades "
            "WHERE COALESCE(exit_date, '') = '' AND exit_price IS NULL "
            "AND key_levels_json IS NOT NULL",
        )
    except Exception as e:
        logger.warning("journal_lifecycle read failed: %s", e)
        return 0

    closed = 0
    today = datetime.now(_ET).date().isoformat()
    for r in rows:
        under = str(r.get("ticker") or "").upper()
        spot = spot_map.get(under)
        if spot is None:
            continue
        try:
            kl = json.loads(r.get("key_levels_json") or "null")
        except (TypeError, ValueError):
            kl = None
        if not isinstance(kl, dict):
            continue
        inv, tgt = kl.get("invalidation"), kl.get("target")
        if inv is None or tgt is None:
            continue
        ctype = str(r.get("type") or "call").lower()
        stop_hit = spot <= float(inv) if ctype == "call" else spot >= float(inv)
        tgt_hit = spot >= float(tgt) if ctype == "call" else spot <= float(tgt)
        if not (stop_hit or tgt_hit):
            continue
        exit_px = float(tgt) if tgt_hit else float(inv)   # target wins ties
        key = "|".join(str(r.get(k) or "") for k in
                       ("ticker", "type", "action", "strike", "expiry", "entry_date"))
        if close_trade(engine, key, exit_price=exit_px, exit_date=today):
            closed += 1
            logger.info("journal lifecycle: %s %s via %s @ %s (spot %s)",
                        under, "TARGET" if tgt_hit else "STOP", key, exit_px, spot)
    return closed


def close_trade(engine, key: str, *, exit_price: float, exit_date: str) -> bool:
    """Set exit fields on the trade matching a journalSeedKey() key."""
    parts = str(key).split("|")
    if len(parts) != 6:
        return False
    ticker, ctype, action, strike, expiry, entry_date = parts
    try:
        strike_f = float(strike) if strike else None
    except ValueError:
        return False

    existing = engine.query(
        "SELECT ticker FROM flow_journal_trades WHERE ticker = ? AND type = ? "
        "AND action = ? AND strike IS NOT DISTINCT FROM ? AND expiry = ? AND entry_date = ?",
        [ticker.upper(), ctype.lower(), action.lower(), strike_f, expiry, entry_date],
    )
    if not existing:
        return False
    engine.execute_write(
        """
        UPDATE flow_journal_trades
        SET exit_price = ?, exit_date = ?, updated_at = current_timestamp
        WHERE ticker = ? AND type = ? AND action = ?
          AND strike IS NOT DISTINCT FROM ? AND expiry = ? AND entry_date = ?
        """,
        [(float(exit_price), exit_date, ticker.upper(), ctype.lower(),
         action.lower(), strike_f, expiry, entry_date)],
    )
    return True


def setup_stats(engine, *, days: int = 90) -> dict:
    """Per-setup win-rate stats over closed trades. A win is
    exit_price >= entry_price for BUY (>= for long calls/puts); losses the
    inverse. Groups by setup label (+ overall), includes gex_regime split."""
    cutoff = f"current_timestamp - INTERVAL '{int(days)}' DAY"
    rows = engine.query(
        f"""SELECT COALESCE(setup, '') AS setup, COALESCE(gex_regime, '') AS regime,
                   action, entry_price, exit_price
            FROM flow_journal_trades
            WHERE NOT (COALESCE(exit_date, '') = '' AND exit_price IS NULL)
              AND entry_price IS NOT NULL AND exit_price IS NOT NULL
              AND updated_at > {cutoff}""",
    )
    def _bucket():
        return {"n": 0, "wins": 0, "losses": 0, "pnl_sum": 0.0}
    by_setup: dict = {}
    by_regime: dict = {}
    overall = _bucket()
    for r in rows:
        entry = float(r["entry_price"])
        exitp = float(r["exit_price"])
        if entry <= 0:
            continue
        ret = (exitp - entry) / entry
        win = exitp >= entry  # all journal entries are BUY-side
        b = by_setup.setdefault(r["setup"] or "(unlabeled)", _bucket())
        g = by_regime.setdefault(r["regime"] or "(unknown)", _bucket())
        for d in (b, g, overall):
            d["n"] += 1
            d["wins"] += 1 if win else 0
            d["losses"] += 0 if win else 1
            d["pnl_sum"] += ret
    def _finalize(d):
        out = {}
        for k, v in d.items():
            n = v.pop("n")
            v["n"] = n
            v["win_rate"] = round(v["wins"] / n, 4) if n else None
            v["avg_return"] = round(v["pnl_sum"] / n, 6) if n else None
            del v["pnl_sum"]
            out[k] = v
        return out
    return {
        "days": int(days),
        "overall": _finalize({"all": overall})["all"],
        "by_setup": _finalize(by_setup),
        "by_gex_regime": _finalize(by_regime),
    }


# ── P1-7 whale tracker (Agent C, 2026-09-05) ──────────────────────────
# Bookmark an alert → live STILL_IN/PARTIAL/EXITED/EXPIRED via Vol/ΔOI
# decay + badge P&L. P&L is the side-signed UNDERLYING-leg move
# (pnl_underlying_pct) — a labeled proxy, not premium P&L (premium needs
# chain mids at scan time; a future pass can attach last_mid).

_WHALE_DDL = """
    CREATE TABLE IF NOT EXISTS whale_tracks (
        asof_date DATE, alert_key TEXT, ckey TEXT, under TEXT,
        type TEXT, side TEXT, bias TEXT, strike DOUBLE, exp TEXT,
        entry_spot DOUBLE, entry_oi DOUBLE, entry_vol DOUBLE,
        last_spot DOUBLE, last_oi DOUBLE, last_vol DOUBLE,
        state TEXT, pnl_underlying_pct DOUBLE, reason TEXT,
        updated_ts TIMESTAMP,
        PRIMARY KEY (asof_date, alert_key)
    )
"""

WHALE_PARTIAL_DROP = 0.10   # OI decay 10-50% → PARTIAL
WHALE_EXIT_DROP = 0.50      # OI collapse >50% → EXITED
WHALE_CLOSER_VOL_MULT = 2.0  # vol burst vs entry…
WHALE_CLOSER_OI_DROP = 0.25  # …with OI decay ≥25% → closer-shape EXITED


def init_whale_tables(engine) -> None:
    engine.execute_write(_WHALE_DDL)


def _side_sign(track: dict) -> int:
    side = str(track.get("side") or track.get("type") or "").lower()
    bias = str(track.get("bias") or "").upper()
    if side.startswith("p") or bias == "BEARISH":
        return -1
    return 1


def whale_state(track: dict, snap: dict) -> dict[str, Any]:
    """Pure state read: bookmark snapshot + live snapshot → state/pnl/reason."""
    try:
        entry_spot = float(track.get("entry_spot") or 0)
        spot = float(snap.get("spot") or 0)
    except (TypeError, ValueError):
        entry_spot, spot = 0.0, 0.0
    pnl = None
    if entry_spot > 0 and spot > 0:
        pnl = round(_side_sign(track) * (spot - entry_spot) / entry_spot * 100.0, 2)
    try:
        dte = snap.get("dte")
        dte = None if dte is None else int(dte)
    except (TypeError, ValueError):
        dte = None
    if dte is not None and dte <= 0:
        return {"state": "EXPIRED", "pnl_underlying_pct": pnl,
                "reason": "past expiry — position closed by time"}
    try:
        entry_oi = float(track.get("entry_oi") or 0)
        oi = float(snap.get("oi") if snap.get("oi") is not None else entry_oi)
    except (TypeError, ValueError):
        entry_oi, oi = 0.0, 0.0
    if entry_oi <= 0:
        return {"state": "STILL_IN", "pnl_underlying_pct": pnl,
                "reason": "no OI basis — held by default"}
    drop = 1.0 - oi / entry_oi
    try:
        entry_vol = float(track.get("entry_vol") or 0)
        vol = float(snap.get("vol") or 0)
    except (TypeError, ValueError):
        entry_vol, vol = 0.0, 0.0
    closer = (entry_vol > 0 and vol >= WHALE_CLOSER_VOL_MULT * entry_vol
              and drop >= WHALE_CLOSER_OI_DROP)
    if drop >= WHALE_EXIT_DROP or closer:
        why = (f"OI collapsed {drop * 100:.0f}% — exited"
               if drop >= WHALE_EXIT_DROP
               else f"closer shape: {vol:,.0f} prints on {drop * 100:.0f}% OI decay")
        return {"state": "EXITED", "pnl_underlying_pct": pnl, "reason": why}
    if drop >= WHALE_PARTIAL_DROP:
        return {"state": "PARTIAL", "pnl_underlying_pct": pnl,
                "reason": f"OI decayed {drop * 100:.0f}% — scaling out"}
    return {"state": "STILL_IN", "pnl_underlying_pct": pnl,
            "reason": f"OI held ({drop * 100:+.0f}%) — still in"}


def bookmark_whale(engine, alert: dict, *, spot: float, oi: float, vol: float) -> int:
    """Idempotent bookmark of a whale alert. Returns 1 added / 0 existing."""
    try:
        asof = str(alert.get("asof") or "")[:10] or datetime.now(_ET).date().isoformat()
        key = str(alert.get("key") or alert.get("ckey") or "")
        if not key:
            return 0
        have = engine.query(
            "SELECT count(*) AS c FROM whale_tracks WHERE asof_date = ? AND alert_key = ?",
            [asof, key])
        if have and int(have[0]["c"]) > 0:
            return 0
        engine.execute_write("""
            INSERT INTO whale_tracks
            (asof_date, alert_key, ckey, under, type, side, bias, strike, exp,
             entry_spot, entry_oi, entry_vol, last_spot, last_oi, last_vol,
             state, pnl_underlying_pct, reason, updated_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
        """, [[asof, key, str(alert.get("ckey") or ""), str(alert.get("under") or "").upper(),
               str(alert.get("type") or "call").lower(), str(alert.get("side") or "BUY"),
               str(alert.get("bias") or ""),
               float(alert.get("strike") or 0), str(alert.get("exp") or ""),
               float(spot or 0), float(oi or 0), float(vol or 0),
               float(spot or 0), float(oi or 0), float(vol or 0),
               "STILL_IN", 0.0, "bookmarked — awaiting first update"]])
        return 1
    except Exception as e:
        logger.debug(f"journal_store.bookmark_whale: {e}")
        return 0


def update_whales(engine, snaps: dict) -> dict[str, dict]:
    """Apply live snapshots {ckey: {spot, oi, vol, dte}} → {ckey: state row}."""
    out: dict[str, dict] = {}
    try:
        rows = engine.query("SELECT * FROM whale_tracks WHERE state != 'EXPIRED'")
    except Exception as e:
        logger.debug(f"journal_store.update_whales read: {e}")
        return out
    for r in rows or []:
        r = dict(r)
        snap = (snaps or {}).get(str(r.get("ckey"))) or {}
        if not snap:
            continue
        track = {"entry_spot": r.get("entry_spot"), "entry_oi": r.get("entry_oi"),
                 "entry_vol": r.get("entry_vol"), "side": r.get("side"),
                 "type": r.get("type"), "bias": r.get("bias")}
        st = whale_state(track, snap)
        with contextlib.suppress(Exception):
            engine.execute_write("""
                UPDATE whale_tracks
                SET last_spot = ?, last_oi = ?, last_vol = ?,
                    state = ?, pnl_underlying_pct = ?, reason = ?,
                    updated_ts = current_timestamp
                WHERE asof_date = ? AND alert_key = ?
            """, [[float(snap.get("spot") or 0), float(snap.get("oi") or 0),
                   float(snap.get("vol") or 0), st["state"], st["pnl_underlying_pct"],
                   st["reason"], str(r.get("asof_date"))[:10], str(r.get("alert_key"))]])
        out[str(r.get("ckey"))] = st
    return out


def read_whales(engine, *, state: str | None = None, days: int = 30) -> list[dict]:
    """Live badge read: open tracks (optionally state-filtered)."""
    try:
        sql = "SELECT * FROM whale_tracks WHERE asof_date >= current_date - INTERVAL '30' DAY"
        params: list = []
        if state:
            sql += " AND state = ?"
            params.append(state)
        sql += " ORDER BY updated_ts DESC"
        return engine.query(sql, params) or []
    except Exception as e:
        logger.debug(f"journal_store.read_whales: {e}")
        return []
