"""
The desk pass — post-eval hardening for the institutional alert engine.

Runs AFTER flow_alerts.eval_institutional and BEFORE dedup/persist. Kept as
a separate module (rather than growing eval) so the pure engine, the quality
factors (flow_quality) and the stateful desk context compose cleanly — and
so concurrent sessions can work the sibling files without collisions.

Four desk disciplines a real flow desk applies that the raw engine cannot:

  1. FRESH INTEREST — cvforge's day_volume is cumulative. Once an alert's
     dedup TTL lapses, the same morning print re-qualifies all afternoon on
     stale volume. Per-contract volume marks turn cumulative volume into
     NEW-contracts-since-last-scan; intraday rules re-fire only on fresh
     interest (arrival intensity, not level).
  2. CAMPAIGN DETECTION — the same contract alerting across multiple prior
     sessions is an institution building a position over days (the FOLLOW
     insight applied per-contract). One-notch tier promotion, with the
     receipt in `why`.
  3. IV CONTEXT — buying into vol at the >=80th percentile of the ticker's
     own history is how retail chases events; informed directional buyers
     prefer cheap vol (product research: "IV percentile < 50% for buyers").
     Directional alerts fired into rich vol demote one notch. The per-day
     median-IV store self-builds from scan rows; the gate self-activates
     once >=5 sessions of history exist.
  4. Everything is annotated, never silent — a desk explains its filters.

DuckDB invariant: all writes via engine.execute_write.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

_INTRADAY_RULES = {"SCORE", "WHALE", "0DTE"}
_FRESH_MIN_ABS = 500        # contracts of new interest to re-qualify
_FRESH_MIN_FRAC = 0.10      # ... or 10% of cumulative volume, whichever larger
_CAMPAIGN_MIN_DAYS = 2      # prior sessions with the same contract alerting
_IV_RICH_PCTILE = 0.80
_IV_MIN_HISTORY = 5

_TIER_UP = {"BRONZE": "SILVER", "SILVER": "GOLD", "GOLD": "GOLD"}
_TIER_DOWN = {"GOLD": "SILVER", "SILVER": "BRONZE", "BRONZE": "BRONZE"}


def init_desk_tables(engine) -> None:
    engine.execute_write("""
        CREATE TABLE IF NOT EXISTS flow_vol_marks (
            ckey TEXT PRIMARY KEY, vol DOUBLE, ts DOUBLE
        )
    """)
    engine.execute_write("""
        CREATE TABLE IF NOT EXISTS flow_iv_daily (
            snapshot_date DATE, under TEXT, atm_iv DOUBLE,
            PRIMARY KEY (snapshot_date, under)
        )
    """)


# ── 1. fresh interest ───────────────────────────────────────────────

def mark_vol_deltas(engine, rows, now: float | None = None) -> dict:
    """{ckey: new volume since the last scan} — None on first sight.

    A drop in cumulative volume means a new session started upstream; the
    full figure counts as fresh. Marks are upserted for every row seen.
    """
    t = time.time() if now is None else now
    out: dict = {}
    rows = [r for r in (rows or []) if r.get("ckey")]
    if not rows:
        return out
    keys = [r["ckey"] for r in rows]
    prev: dict = {}
    try:
        ph = ",".join("?" for _ in keys)
        prev = {x["ckey"]: x["vol"] for x in engine.query(
            f"SELECT ckey, vol FROM flow_vol_marks WHERE ckey IN ({ph})", keys)}
    except Exception as e:
        logger.debug(f"flow_desk.mark_vol_deltas read: {e}")
    for r in rows:
        vol = r.get("vol") or 0.0
        p = prev.get(r["ckey"])
        if p is None:
            out[r["ckey"]] = None
        elif vol < p:
            out[r["ckey"]] = vol            # session rollover
        else:
            out[r["ckey"]] = vol - p
    try:
        engine.execute_write("""
            INSERT INTO flow_vol_marks (ckey, vol, ts) VALUES (?, ?, ?)
            ON CONFLICT (ckey) DO UPDATE SET vol = excluded.vol, ts = excluded.ts
        """, [[r["ckey"], r.get("vol") or 0.0, t] for r in rows])
    except Exception as e:
        logger.debug(f"flow_desk.mark_vol_deltas write: {e}")
    return out


def fresh_gate(alerts, deltas, min_abs: float = _FRESH_MIN_ABS,
               min_frac: float = _FRESH_MIN_FRAC) -> list:
    """Keep intraday alerts only when their contract shows fresh interest.

    Confirmation rules (OICONF, SIGMA) carry different evidence and are
    exempt. Unknown delta (first sight) never gates.
    """
    kept = []
    for a in alerts or []:
        if a.get("rule") not in _INTRADAY_RULES:
            kept.append(a)
            continue
        d = (deltas or {}).get(a.get("ckey"))
        if d is None:
            kept.append(a)
            continue
        strike = a.get("strike") or 0
        vol = (a.get("notional") or 0) / (100 * strike) if strike else 0
        need = max(min_abs, min_frac * vol)
        if d >= need:
            kept.append(a)
    return kept


# ── 2. campaign detection ───────────────────────────────────────────

def read_prior_alert_days(engine, ckeys, lookback_days: int = 10) -> dict:
    """{ckey: number of DISTINCT prior sessions this contract alerted}."""
    if not ckeys:
        return {}
    today = datetime.now(_ET).date().isoformat()
    since = (datetime.now(_ET).date() - timedelta(days=lookback_days)).isoformat()
    try:
        ph = ",".join("?" for _ in ckeys)
        rows = engine.query(f"""
            SELECT ckey, count(DISTINCT asof_date) AS n
            FROM flow_alerts_daily
            WHERE ckey IN ({ph}) AND asof_date >= ? AND asof_date < ?
            GROUP BY ckey
        """, list(ckeys) + [since, today])
        return {r["ckey"]: int(r["n"]) for r in rows}
    except Exception as e:
        logger.debug(f"flow_desk.read_prior_alert_days: {e}")
        return {}


def apply_campaign(alerts, prior_days, min_days: int = _CAMPAIGN_MIN_DAYS) -> int:
    """Promote directional alerts whose contract has a multi-session history."""
    n = 0
    for a in alerts or []:
        if not a.get("bias"):
            continue
        d = (prior_days or {}).get(a.get("ckey")) or 0
        if d >= min_days:
            a["tier"] = _TIER_UP.get(a.get("tier"), a.get("tier"))
            a["why"] = (a.get("why") or "") + f" · campaign: day {d + 1} of positioning in this contract"
            n += 1
    return n


# ── 2b. earnings protocol (C5, C-side) ──────────────────────────────────
# Muravyev-Pearson direction: anneal, don't demote. Earnings-window alerts
# still fire but route to the event protocol — flag (drives the C3 1%
# sizing cap), 1.5x wider invalidation, event-day exit note. Never removes.
_EARNINGS_STOP_WIDEN = 1.5


def apply_earnings_protocol(alerts, oi_tags) -> int:
    """Flag + widen earnings-window alerts. Returns count routed."""
    n = 0
    for a in alerts or []:
        tag = (oi_tags or {}).get(a.get("ckey")) or {}
        if not isinstance(tag.get("earnings"), dict):
            continue
        a["earnings_protocol"] = True
        kl = a.get("key_levels")
        if isinstance(kl, dict):
            try:
                entry, inv = float(kl["entry"]), float(kl["invalidation"])
                kl["invalidation"] = round(entry - (entry - inv) * _EARNINGS_STOP_WIDEN, 4)
            except (TypeError, ValueError, KeyError):
                pass
        a["why"] = (a.get("why") or "") + " · earnings protocol: reduced size, wider stop, exit by event day"
        n += 1
    return n


# ── 3. IV context ───────────────────────────────────────────────────

def record_iv_daily(engine, rows, snapshot_date: str | None = None) -> int:
    """Upsert each ticker's median row IV for the session. Self-building."""
    day = snapshot_date or datetime.now(_ET).date().isoformat()
    by_under: dict[str, list] = {}
    for r in rows or []:
        if r.get("iv") is not None:
            by_under.setdefault(r["under"], []).append(r["iv"])
    if not by_under:
        return 0
    payload = []
    for under, ivs in by_under.items():
        ivs.sort()
        mid = len(ivs) // 2
        med = ivs[mid] if len(ivs) % 2 else (ivs[mid - 1] + ivs[mid]) / 2
        payload.append([day, under, med])
    try:
        engine.execute_write("""
            INSERT INTO flow_iv_daily (snapshot_date, under, atm_iv) VALUES (?, ?, ?)
            ON CONFLICT (snapshot_date, under) DO UPDATE SET atm_iv = excluded.atm_iv
        """, payload)
    except Exception as e:
        logger.debug(f"flow_desk.record_iv_daily: {e}")
    return len(payload)


def iv_context(engine, alerts, snapshot_date: str | None = None,
               min_history: int = _IV_MIN_HISTORY,
               rich_pctile: float = _IV_RICH_PCTILE) -> int:
    """Demote directional alerts fired into the ticker's own rich vol."""
    day = snapshot_date or datetime.now(_ET).date().isoformat()
    n = 0
    for under in {a.get("under") for a in alerts or [] if a.get("bias")}:
        try:
            hist = [r["atm_iv"] for r in engine.query(
                "SELECT atm_iv FROM flow_iv_daily WHERE under = ? AND snapshot_date < ? ORDER BY snapshot_date",
                [under, day])]
            today_row = engine.query(
                "SELECT atm_iv FROM flow_iv_daily WHERE under = ? AND snapshot_date = ?",
                [under, day])
        except Exception as e:
            logger.debug(f"flow_desk.iv_context({under}): {e}")
            continue
        if len(hist) < min_history or not today_row:
            continue
        today_iv = today_row[0]["atm_iv"]
        pct = sum(1 for h in hist if h <= today_iv) / len(hist)
        if pct >= rich_pctile:
            for a in alerts:
                if a.get("under") == under and a.get("bias"):
                    a["tier"] = _TIER_DOWN.get(a.get("tier"), a.get("tier"))
                    a["why"] = (a.get("why") or "") + f" · IV at p{round(pct * 100)} of its own history — rich-vol entry"
                    n += 1
    return n


# ── orchestrator ────────────────────────────────────────────────────

def desk_pass(engine, rows, alerts, now: float | None = None, oi_tags: dict | None = None) -> list:
    """The full desk pass: fresh-interest gate → campaign promotion →
    earnings protocol → IV-context demotion. Returns the surviving (annotated) alerts."""
    try:
        init_desk_tables(engine)
        deltas = mark_vol_deltas(engine, rows, now=now)
        alerts = fresh_gate(alerts, deltas)
        if alerts:
            prior = read_prior_alert_days(engine, [a["ckey"] for a in alerts if a.get("ckey")])
            apply_campaign(alerts, prior)
        if alerts and oi_tags:
            apply_earnings_protocol(alerts, oi_tags)
        record_iv_daily(engine, rows)
        if alerts:
            iv_context(engine, alerts)
        return alerts
    except Exception as e:
        logger.warning(f"flow_desk.desk_pass failed open (alerts passed through): {e}")
        return alerts or []
