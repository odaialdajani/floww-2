"""
backend/services/flow_outcomes.py

Outcome-measurement layer for the institutional flow-alert engine ("does the
tape actually predict?"). Joins the persisted alert ledger
(flow_alerts_daily, written by services/flow_alerts.py) to subsequent
underlying returns and produces per-rule, control-matched precision stats.

Why: every alert threshold in the system (SCORE≥92, WHALE≥$25M, SIGMA≥6σ…)
is currently a hand-picked default. This module is the foundation for tuning
those thresholds from measured hit rates instead of intuition.

Design (desk-standard, mirrors the Kimi plan #1):

  • Unit of analysis = ONE alert row (already deduped per (asof_date, key) —
    see flow_alerts_daily PRIMARY KEY). Ticker-day clustering is handled by
    block-bootstrap resampling CLUSTERS, not rows.
  • Label y = 1 if the side-signed cumulative underlying return over the
    next N trading sessions reached k·σ20 (vol-scaled threshold), where the
    return direction is +1 for call-side alerts (bias BULLISH) and −1 for
    put-side (bias BEARISH). Censored windows (fewer than N forward sessions
    of bars available) are EXCLUDED from stats, never zero-filled.
  • Control cohort: for each alert (ticker, date), sample up to
    `control_per_alert` non-alert ticker-dates within ±`control_window_days`
    calendar days, matched on VIX tercile when a VIX series is supplied
    (fallback: unmatched). Controls are labeled with the SAME rule — i.e.
    "what did non-alert SPY days do over the same window?" — so lift =
    precision − control_rate is an apples-to-apples excess-hit-rate read.
  • σ20 (daily realized vol stdev of log returns) is computed from the same
    supplied bars, trailing 20 sessions ending the day BEFORE the alert.
  • MFE/MAE (max favorable / adverse excursion, side-signed, in σ units)
    over the N-session window, for payoff-asymmetry reads.

No network calls here — the caller supplies bars:
    bars: {ticker: [(date_iso, close), ...]} ascending by date
    vix:  [(date_iso, close), ...] ascending, optional

All numbers that depend on sample size are None below `min_alerts` — honest
empty state, never a fabricated precision on n=2.

DuckDB invariant: read-only against flow_alerts_daily; no writes.
"""

from __future__ import annotations

import logging
import math
import random
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ── tunables (thresholds live in flow_alerts; these are measurement params) ──
DEFAULT_HORIZON_SESSIONS = 2      # N: forward sessions to measure (Pan-Poteshman next-day power → N=2 primary)
DEFAULT_SIGMA_K = 0.75            # hit = |side-signed cum return| ≥ k·σ20
DEFAULT_SIGMA_WINDOW = 20         # trailing sessions for σ20
DEFAULT_CONTROL_PER_ALERT = 20    # matched controls per alert ticker-day
DEFAULT_CONTROL_WINDOW_DAYS = 45  # ±calendar days for the control search
DEFAULT_MIN_ALERTS = 5            # below this: precision/lift are None (uncalibrated)
DEFAULT_BOOTSTRAP_ITERS = 500     # block (cluster) bootstrap iterations
DEFAULT_BOOTSTRAP_SEED = 42       # deterministic CIs for reproducible dashboards
DEFAULT_LOOKBACK_DAYS = 60        # how much alert history to measure per run


# ── bars helpers ─────────────────────────────────────────────────────────────

def _index_bars(bars: dict[str, list[tuple[str, float]]]) -> dict[str, dict[str, float]]:
    """{ticker: [(date, close), ...]} → {ticker: {date: close}} (ascending assumed)."""
    out: dict[str, dict[str, float]] = {}
    for tkr, series in (bars or {}).items():
        out[tkr] = {str(d): float(c) for d, c in series if d is not None and c is not None}
    return out


def _trading_dates_after(dates_asc: list[str], start_date: str, n: int) -> list[str]:
    """First n trading dates strictly AFTER start_date (dates_asc is ascending ISO)."""
    try:
        i = _bisect_right(dates_asc, start_date)
    except Exception:
        return []
    return dates_asc[i:i + n]


def _bisect_right(sorted_dates: list[str], target: str) -> int:
    lo, hi = 0, len(sorted_dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_dates[mid] <= target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _sigma20(bars_by_date: dict[str, float], dates_asc: list[str], asof: str,
             window: int = DEFAULT_SIGMA_WINDOW) -> float | None:
    """Trailing `window`-session log-return stdev ending the session BEFORE asof."""
    i = _bisect_right(dates_asc, asof)
    hist = dates_asc[max(0, i - window - 1):i]
    if len(hist) < window:  # need window returns → window+1 closes
        return None
    rets = []
    for a, b in zip(hist, hist[1:], strict=False):
        try:
            if bars_by_date[a] > 0 and bars_by_date[b] > 0:
                rets.append(math.log(bars_by_date[b] / bars_by_date[a]))
        except Exception:
            continue
    if len(rets) < window - 1:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
    return math.sqrt(var) or None


def _forward_path(bars_by_date: dict[str, float], dates_asc: list[str], asof: str,
                  entry_price: float, n: int, side_sign: int) -> dict[str, Any] | None:
    """Side-signed forward returns over the n sessions after asof.

    Returns None when censored (< n forward sessions — excluded, never zero-filled).
    """
    fwd = _trading_dates_after(dates_asc, asof, n)
    if len(fwd) < n:
        return None
    path = []
    for d in fwd:
        px = bars_by_date.get(d)
        if not px or not entry_price:
            return None
        path.append(side_sign * (px / entry_price - 1.0))
    cum = path[-1]
    # side-signed MFE/MAE in return space (not yet σ units — caller scales)
    peak, trough = path[0], path[0]
    for r in path:
        peak = max(peak, r)
        trough = min(trough, r)
    return {"cum": cum, "peak": peak, "trough": trough, "sessions": len(path)}


def _vix_tercile(vix: list[tuple[str, float]] | None, asof: str) -> int | None:
    """VIX tercile (0/1/2) as of `asof` using the full supplied series' terciles."""
    if not vix:
        return None
    vals = sorted(float(c) for _, c in vix)
    if len(vals) < 9:
        return None
    q1, q2 = vals[len(vals) // 3], vals[2 * len(vals) // 3]
    px = None
    for d, c in vix:  # series ascending: last ≤ asof wins
        if str(d) <= asof:
            px = float(c)
        else:
            break
    if px is None:
        return None
    if px <= q1:
        return 0
    if px <= q2:
        return 1
    return 2


# ── labeling ─────────────────────────────────────────────────────────────────

def label_alerts(
    alerts: list[dict[str, Any]],
    bars: dict[str, list[tuple[str, float]]],
    vix: list[tuple[str, float]] | None = None,
    *,
    horizon: int = DEFAULT_HORIZON_SESSIONS,
    sigma_k: float = DEFAULT_SIGMA_K,
    sigma_window: int = DEFAULT_SIGMA_WINDOW,
) -> list[dict[str, Any]]:
    """Attach outcome labels to alert rows.

    Each alert gains: sigma20, hit (bool|None), ret (float|None),
    mfe_sigma / mae_sigma (float|None), censored (bool), vix_tercile.
    Side sign: call-side +1, put-side −1 (from `side` or `type`).
    """
    indexed = _index_bars(bars)
    dates_by_tkr = {t: sorted(m.keys()) for t, m in indexed.items()}

    out = []
    for a in alerts or []:
        under = (a.get("under") or "").upper()
        asof = str(a.get("asof_date") or "")[:10]
        row = dict(a)
        row.update({"sigma20": None, "hit": None, "ret": None,
                    "mfe_sigma": None, "mae_sigma": None, "censored": True,
                    "vix_tercile": _vix_tercile(vix, asof)})
        m = indexed.get(under)
        if not m or asof not in m:
            out.append(row)
            continue
        dates_asc = dates_by_tkr.get(under, [])
        sig = _sigma20(m, dates_asc, asof, sigma_window)
        row["sigma20"] = sig
        side_raw = str(a.get("side") or a.get("type") or "").lower()
        side_sign = -1 if side_raw.startswith("p") or side_raw == "bearish" else 1
        entry = float(a.get("under_price") or 0) or m.get(asof)
        path = _forward_path(m, dates_asc, asof, entry, horizon, side_sign)
        if path is None:
            out.append(row)
            continue
        row["censored"] = False
        row["ret"] = path["cum"]
        if sig:
            row["hit"] = abs(path["cum"]) >= sigma_k * sig
            row["mfe_sigma"] = path["peak"] / sig
            row["mae_sigma"] = path["trough"] / sig
        else:
            # no vol context → absolute floor: 1% move counts as a hit (documented)
            row["hit"] = abs(path["cum"]) >= 0.01
        out.append(row)
    return out


# ── control cohort ───────────────────────────────────────────────────────────

def build_controls(
    labeled: list[dict[str, Any]],
    bars: dict[str, list[tuple[str, float]]],
    vix: list[tuple[str, float]] | None = None,
    *,
    horizon: int = DEFAULT_HORIZON_SESSIONS,
    sigma_k: float = DEFAULT_SIGMA_K,
    sigma_window: int = DEFAULT_SIGMA_WINDOW,
    per_alert: int = DEFAULT_CONTROL_PER_ALERT,
    window_days: int = DEFAULT_CONTROL_WINDOW_DAYS,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """Control cohort: non-alert ticker-days, same labeling machinery.

    For each labeled alert, sample up to `per_alert` candidate (ticker, date)
    days within ±window_days that (a) have no alert that day for that ticker,
    (b) match the alert's VIX tercile when both are known. Deterministic given
    the same rng seed.
    """
    rng = rng or random.Random(DEFAULT_BOOTSTRAP_SEED)
    indexed = _index_bars(bars)
    dates_by_tkr = {t: sorted(m.keys()) for t, m in indexed.items()}
    alert_days: set[tuple[str, str]] = {
        ((a.get("under") or "").upper(), str(a.get("asof_date") or "")[:10])
        for a in labeled
    }
    # tercile lookup per (ticker, date) for matching
    controls: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()  # (rule, ticker, date) dedup

    for a in labeled or []:
        under = (a.get("under") or "").upper()
        asof = str(a.get("asof_date") or "")[:10]
        rule = a.get("rule") or "UNKNOWN"
        m = indexed.get(under)
        if not m:
            continue
        dates_asc = dates_by_tkr.get(under, [])
        try:
            d0 = date.fromisoformat(asof)
        except ValueError:
            continue
        lo, hi = d0 - timedelta(days=window_days), d0 + timedelta(days=window_days)
        candidates = [
            d for d in dates_asc
            if lo <= date.fromisoformat(d) <= hi and (under, d) not in alert_days
        ]
        terc = a.get("vix_tercile")
        if terc is not None and vix:
            matched = [d for d in candidates if _vix_tercile(vix, d) == terc]
            if matched:
                candidates = matched
        rng.shuffle(candidates)
        for d in candidates[:per_alert]:
            ck = (rule, under, d)
            if ck in seen:
                continue
            seen.add(ck)
            sig = _sigma20(m, dates_asc, d, sigma_window)
            side_sign = 1 if str(a.get("side") or a.get("type") or "").lower().startswith("c") else -1
            path = _forward_path(m, dates_asc, d, m.get(d, 0.0), horizon, side_sign)
            c = {
                "rule": rule, "under": under, "asof_date": d, "side": a.get("side"),
                "is_control": True, "sigma20": sig, "censored": True,
                "hit": None, "ret": None, "mfe_sigma": None, "mae_sigma": None,
                "vix_tercile": _vix_tercile(vix, d),
            }
            if path is not None:
                c["censored"] = False
                c["ret"] = path["cum"]
                c["hit"] = (abs(path["cum"]) >= sigma_k * sig) if sig else (abs(path["cum"]) >= 0.01)
                if sig:
                    c["mfe_sigma"] = path["peak"] / sig
                    c["mae_sigma"] = path["trough"] / sig
            controls.append(c)
    return controls


# ── stats ────────────────────────────────────────────────────────────────────

def _wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _block_bootstrap_lift(
    alert_hits: list[bool],
    alert_clusters: list[str],
    control_hits: list[bool],
    control_clusters: list[str],
    iters: int,
    rng: random.Random,
) -> tuple[float, float] | None:
    """95% CI for (precision − control_rate) via cluster bootstrap.

    Resamples CLUSTERS (ticker-days), not rows — alert bursts on one ticker-day
    are correlated and would otherwise fake tight CIs.
    """
    if not alert_hits or not control_hits:
        return None

    def _clusters(hits: list[bool], clusters: list[str]) -> list[tuple[str, list[bool]]]:
        by: dict[str, list[bool]] = {}
        for c, h in zip(clusters, hits, strict=False):
            by.setdefault(c, []).append(h)
        return list(by.items())

    a_cl = _clusters(alert_hits, alert_clusters)
    c_cl = _clusters(control_hits, control_clusters)
    if not a_cl or not c_cl:
        return None

    def _rate(pooled: list[bool]) -> float:
        return sum(pooled) / len(pooled) if pooled else 0.0

    diffs = []
    for _ in range(iters):
        a_pool = [h for _, hs in (a_cl[rng.randrange(len(a_cl))] for _ in range(len(a_cl))) for h in hs]
        c_pool = [h for _, hs in (c_cl[rng.randrange(len(c_cl))] for _ in range(len(c_cl))) for h in hs]
        if a_pool and c_pool:
            diffs.append(_rate(a_pool) - _rate(c_pool))
    if len(diffs) < iters // 2:
        return None
    diffs.sort()
    return (diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs))])


def outcome_stats(
    labeled: list[dict[str, Any]],
    controls: list[dict[str, Any]] | None = None,
    *,
    min_alerts: int = DEFAULT_MIN_ALERTS,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Per-rule precision, control rate, lift, CI, payoff stats.

    Honest-empty-state contract: rules below `min_alerts` MEASURED alerts get
    precision=None (the UI renders "uncalibrated: n=k", never a fake number).
    """
    rng = rng or random.Random(DEFAULT_BOOTSTRAP_SEED)
    # Censored rows are KEPT in by_rule (for honest n_censored accounting) but
    # excluded from every hits/return list below — excluded, never zero-filled.
    by_rule: dict[str, list[dict]] = {}
    for a in labeled or []:
        by_rule.setdefault(a.get("rule") or "UNKNOWN", []).append(a)
    ctrl_by_rule: dict[str, list[dict]] = {}
    for c in controls or []:
        if c.get("censored"):
            continue
        ctrl_by_rule.setdefault(c.get("rule") or "UNKNOWN", []).append(c)

    per_rule = {}
    overall_hits = overall_n = 0
    for rule, rows in sorted(by_rule.items()):
        measured_rows = [r for r in rows if not r.get("censored")]
        hits = [bool(r["hit"]) for r in measured_rows if r.get("hit") is not None]
        n = len(hits)
        h = sum(hits)
        precision = h / n if n >= min_alerts else None
        ci = _wilson_ci(h, n) if n else None

        crows = ctrl_by_rule.get(rule, [])
        chits = [bool(r["hit"]) for r in crows if r.get("hit") is not None]
        cn, ch = len(chits), sum(chits)
        control_rate = ch / cn if cn else None
        lift = (precision - control_rate) if (precision is not None and control_rate is not None) else None
        lift_ci = _block_bootstrap_lift(
            hits, [r["under"] + "|" + str(r["asof_date"]) for r in rows if r.get("hit") is not None],
            chits, [r["under"] + "|" + str(r["asof_date"]) for r in crows if r.get("hit") is not None],
            bootstrap_iters, rng,
        ) if lift is not None else None

        mfe = [r["mfe_sigma"] for r in measured_rows if r.get("mfe_sigma") is not None]
        mae = [r["mae_sigma"] for r in measured_rows if r.get("mae_sigma") is not None]

        per_rule[rule] = {
            "n_alerts": len(rows),
            "n_measured": n,
            "n_censored": len(rows) - len(measured_rows),
            "n_controls": cn,
            "hits": h,
            "precision": round(precision, 4) if precision is not None else None,
            "precision_ci": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
            "control_rate": round(control_rate, 4) if control_rate is not None else None,
            "lift": round(lift, 4) if lift is not None else None,
            "lift_ci": [round(lift_ci[0], 4), round(lift_ci[1], 4)] if lift_ci else None,
            "median_mfe_sigma": round(sorted(mfe)[len(mfe) // 2], 3) if mfe else None,
            "median_mae_sigma": round(sorted(mae)[len(mae) // 2], 3) if mae else None,
            "uncalibrated": n < min_alerts,
            # Rule-decay governance (2026-09-02): ledger-driven status. Display
            # only — thresholds stay the desk's dials, nothing auto-tuned.
            **_decay_status(lift, rows),
        }
        overall_hits += h
        overall_n += n

    measured = [r for rows in by_rule.values() for r in rows if not r.get("censored")]
    censored = sum(1 for rows in by_rule.values() for r in rows if r.get("censored"))
    return {
        "horizon_sessions": None,  # filled by caller (route knows its params)
        "generated_from": {"alerts": len(labeled or []), "measured": len(measured), "censored": censored},
        "min_alerts": min_alerts,
        "overall": {
            "n_measured": overall_n,
            "precision": round(overall_hits / overall_n, 4) if overall_n >= min_alerts else None,
        },
        "per_rule": per_rule,
    }


def compute_outcomes(
    alerts: list[dict[str, Any]],
    bars: dict[str, list[tuple[str, float]]],
    vix: list[tuple[str, float]] | None = None,
    *,
    horizon: int = DEFAULT_HORIZON_SESSIONS,
    sigma_k: float = DEFAULT_SIGMA_K,
    sigma_window: int = DEFAULT_SIGMA_WINDOW,
    per_alert: int = DEFAULT_CONTROL_PER_ALERT,
    window_days: int = DEFAULT_CONTROL_WINDOW_DAYS,
    min_alerts: int = DEFAULT_MIN_ALERTS,
    bootstrap_iters: int = DEFAULT_BOOTSTRAP_ITERS,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """One-shot: label → controls → stats. This is what the route calls."""
    labeled = label_alerts(alerts, bars, vix, horizon=horizon, sigma_k=sigma_k, sigma_window=sigma_window)
    controls = build_controls(labeled, bars, vix, horizon=horizon, sigma_k=sigma_k,
                              sigma_window=sigma_window, per_alert=per_alert,
                              window_days=window_days, rng=random.Random(seed))
    stats = outcome_stats(labeled, controls, min_alerts=min_alerts,
                          bootstrap_iters=bootstrap_iters, rng=random.Random(seed))
    stats["horizon_sessions"] = horizon
    stats["sigma_k"] = sigma_k
    return stats


def _decay_status(lift: float | None, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Governance status from the ledger itself: a rule whose lift sits below
    1.0 across the last 30 days of measured alerts is AMBER (display/status
    only — thresholds are the desk's dials, never auto-tuned)."""
    import datetime as _dt

    if lift is None:
        return {"status": "OK", "decayed": False}
    cutoff = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
    recent = [r for r in rows
              if str(r.get("asof_date") or "")[:10] >= cutoff
              and r.get("hit") is not None and not r.get("censored")]
    if len(recent) < 10:
        return {"status": "OK", "decayed": False}   # too thin to judge
    recent_hits = sum(1 for r in recent if r["hit"])
    if recent_hits / len(recent) < lift:   # precision below the rule's own lift line
        return {"status": "AMBER", "decayed": True}
    return {"status": "OK", "decayed": False}


def read_alert_history(engine: Any, days: int = DEFAULT_LOOKBACK_DAYS) -> list[dict[str, Any]]:
    """Read the persisted alert ledger (flow_alerts_daily) for measurement.

    Read-only — the DuckDB invariant (writes only via execute_write) is
    untouched; this module never writes. Uses engine.query (returns
    list[dict]) per the DuckDBEngine contract.
    """
    try:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = engine.query(
            "SELECT * FROM flow_alerts_daily WHERE asof_date >= ?",
            [cutoff],
        )
        out = []
        for d in rows or []:
            d = dict(d)
            d["asof_date"] = str(d.get("asof_date") or "")[:10]
            out.append(d)
        return out
    except Exception as e:
        logger.warning("flow_outcomes: could not read flow_alerts_daily: %s", e)
        return []


def fetch_bars_yfinance(tickers: list[str], period_days: int = 90) -> dict[str, list[tuple[str, float]]]:
    """Daily closes per ticker via yfinance (free, zero cvforge budget)."""
    out: dict[str, list[tuple[str, float]]] = {}
    try:
        import yfinance as yf
        for t in sorted({(x or "").upper() for x in tickers if x}):
            try:
                hist = yf.Ticker(t).history(period=f"{period_days}d", interval="1d", auto_adjust=True)
                if hist is None or hist.empty:
                    continue
                idx = [str(i.date()) for i in hist.index]
                out[t] = list(zip(idx, [float(c) for c in hist["Close"].tolist()], strict=False))
            except Exception:
                continue
    except Exception as e:
        logger.warning("flow_outcomes: yfinance bars unavailable: %s", e)
    return out
