"""Public options-snapshot scanner over the provider's option-enabled directory.

A rotating cursor visits all supported names. Results retain a one-minute
freshness window, bounded rows and expiry depth; coverage reports distinguish
unvisited, failed and fresh names. This is not an all-market trade tape.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from services.flow_signing import sign_print as _sign_print
from services.roll_spread import roll_pooled_for as _roll_pooled_for
from services.scan_observations import (
    SnapshotObservations,
    eligible_quote,
    quote_time,
    select_observations,
    session_day,
    timestamp,
    unique_contracts,
    volume_change,
)

try:
    from services.market_bars import get_adv_21d as _get_adv
except Exception:  # pragma: no cover - import-time safety
    _get_adv = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# ── Universe ──────────────────────────────────────────────────────────
# ETFs/index proxies + mega-cap flow names + high-beta mid-caps where
# institutional building hides below the top-300-by-volume cutoff.
# No ^SPX-style index symbols: the Public adapter normalizes by stripping ^
# only, and index-option symbology differs by venue — equities/ETFs only.
UNIVERSE: list[str] = [
    # Index / sector ETFs (12)
    "SPY", "QQQ", "IWM", "DIA", "TLT", "XLF", "XLE", "XLK",
    "XBI", "SMH", "GDX", "EWZ",
    # Mega-cap flow names (14)
    "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD",
    "AVGO", "MU", "PLTR", "NFLX", "CRM", "ORCL",
    # High-beta mid-caps — the SNDK/DVN hunting ground (14)
    "SNDK", "DVN", "MSTR", "GME", "APP", "HOOD", "SOFI", "COIN",
    "SMCI", "MARA", "UPST", "AFRM", "DKNG", "RIOT",
]


def get_universe() -> list[str]:
    """Active scan universe — FLOWW_PUBLIC_UNIVERSE (comma-separated) wins,
    else the cached option-enabled provider catalog. Env override reshapes coverage
    without a deploy.

    Entries are uppercased, deduped, and validated (B7): anything that is
    not 1–12 chars of A–Z/0–9/./- is rejected with a warning, never a
    crash — a typo in env must not take down the sweep loop.
    """
    raw = os.environ.get("FLOWW_PUBLIC_UNIVERSE", "")
    names = [t.strip().upper() for t in raw.split(",") if t.strip()]
    # Dedupe, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for t in names:
        if t in seen:
            continue
        seen.add(t)
        if (not t[0].isalpha() or len(t) > 12
                or not all(ch.isalnum() or ch in ".-" for ch in t)):
            log.warning("public scanner dropping invalid universe ticker %r", t)
            continue
        out.append(t)
    if raw.strip():
        return out
    from services.market_catalog import cached_scan_symbols
    symbols = list(dict.fromkeys(cached_scan_symbols()))
    available = set(symbols)
    priority = [name for name in UNIVERSE if name in available]
    priority_names = set(priority)
    # Start with useful liquid names while retaining every provider symbol
    # exactly once in the same fair rotation. Explicit universes keep order.
    return priority + [name for name in symbols if name not in priority_names]


SCAN_COLUMNS: list[str] = [
    "underlying_ticker", "ticker", "contract_type", "strike_price",
    "expiration_date", "day_volume", "open_interest",
    "implied_volatility", "delta", "underlying_price",
]

# Emission floor: vol >= 200 with vol/OI >= 1.0 (fresh positioning), or any
# line with vol >= 2500 (size speaks even against big OI). Caps per ticker
# keep one hot name from eating the merged payload.
MIN_VOL = 200
MIN_VOL_OI = 1.0
BIG_VOL = 2500
MAX_ROWS_PER_TICKER = 60

# Slice cache TTL: a slice older than this is dropped from the merged view
# rather than served as if fresh (honesty over coverage).
SLICE_TTL_S = 60.0

# Upstream fan-out per ticker chain fetch (B4): expirations + quotes +
# one chain call per expiry. Debited per ticker so the 60/min assumption
# stays honest under fan-out.
CHAIN_OVERHEAD_CALLS = 2


def chain_cost(max_expiries: int) -> int:
    """Upstream HTTP calls one ticker chain fetch fans out to."""
    return CHAIN_OVERHEAD_CALLS + max(0, int(max_expiries))


# ── Pure helpers ──────────────────────────────────────────────────────

def advance_cursor(cursor: int, slice_size: int, n: int) -> tuple[list[int], int]:
    """Indices for the next slice + the rotated cursor. Pure (tested)."""
    if n <= 0 or slice_size <= 0:
        return [], cursor
    idx = [(cursor + k) % n for k in range(min(slice_size, n))]
    return idx, (cursor + len(idx)) % n


def ckey_of(under: str, ctype: str, strike: float, exp: str) -> str:
    """Contract identity — MUST match flow_alerts.norm_rows ckey
    (f"{under}|{typ}|{strike:g}|{exp}") and the frontend keyOf, so extras
    join rows on both sides without a translation layer."""
    with contextlib.suppress(TypeError, ValueError):
        return f"{under}|{ctype}|{float(strike):g}|{exp}"
    return f"{under}|{ctype}|{strike}|{exp}"


def nbbo_side(
    last: float | None,
    bid: float | None,
    ask: float | None,
) -> str | None:
    """Aggressor side from NBBO truth (whale-options discipline).

    last at/above ask = buyer lifted (ASK); at/below bid = seller hit (BID);
    mid-print or no two-sided quote = None (unknown — the caller falls back
    to the vol/OI proxy and must label it as such, never as NBBO fact).
    """
    try:
        last_f = float(last) if last is not None else None
        b = float(bid) if bid is not None else None
        a = float(ask) if ask is not None else None
    except (TypeError, ValueError):
        return None
    if last_f is None or last_f <= 0 or b is None or a is None or a <= b or b <= 0:
        return None
    if last_f >= a:
        return "ASK"
    if last_f <= b:
        return "BID"
    return None


def side_bias(ctype: str, side: str | None) -> tuple[str, str | None]:
    """(side, bias) from contract type + NBBO aggressor.

    ASK = buyer-initiated, BID = seller-initiated; direction follows the
    classic desk read: lifting calls / hitting puts is bullish flow, lifting
    puts / hitting calls is bearish. Unknown side → unlabeled FLOW.
    """
    if side == "ASK":
        return "BUY", ("BULLISH" if ctype == "call" else "BEARISH")
    if side == "BID":
        return "SELL", ("BEARISH" if ctype == "call" else "BULLISH")
    return "FLOW", None


def dealer_context(
    contracts: list[dict[str, Any]],
    spot: float,
    adv_shares: float | None = None,
) -> dict[str, Any]:
    """Per-ticker dealer positioning from real gamma×OI (zero extra calls).

    Dealer-signed net gamma (dealers are structurally short options):
    negative = dealers short gamma → hedging AMPLIFIES moves (the regime in
    which institutional flow chases); positive = dampens (flow mean-reverts
    toward walls). Walls = max-OI strike per side.

    adv_shares (21-session average daily share volume, measured via the C13
    bars provider) unlocks the Barbon-Buraschi ΓIB percentage:
    pct = net_gex / (spot² × 0.01 × adv) × 100 — the same normalization as
    gex_paper_accurate.compute_gamma_imbalance. Without ADV the pct stays
    None (unknown magnitude, never a fabricated zero) while regime still
    propagates from the sign of net gamma.
    """
    call_oi: dict[float, float] = {}
    put_oi: dict[float, float] = {}
    net_gex = 0.0
    have_gamma = False
    try:
        s = float(spot) or 0
    except (TypeError, ValueError):
        s = 0
    for c in contracts or []:
        try:
            if not isinstance(c, dict):
                continue
            k = float(c.get("strike") or 0)
            oi = float(c.get("oi") or 0)
            if k <= 0 or oi <= 0:
                continue
            typ = str(c.get("type") or "").lower()
            bucket = call_oi if typ.startswith("c") else put_oi
            bucket[k] = bucket.get(k, 0.0) + oi
            g = c.get("gamma")
            if g is not None and s > 0:
                gf = float(g)
                net_gex += -gf * oi * 100 * s * s * 0.01
                have_gamma = True
        except (TypeError, ValueError):
            continue
    call_wall = max(call_oi, key=lambda k: call_oi[k]) if call_oi else None
    put_wall = max(put_oi, key=lambda k: put_oi[k]) if put_oi else None
    all_oi = {**call_oi}
    for k, v in put_oi.items():
        all_oi[k] = all_oi.get(k, 0.0) + v
    max_oi_strike = max(all_oi, key=lambda k: all_oi[k]) if all_oi else None
    regime = None
    gib_pct: float | None = None
    adv: float | None = None
    if have_gamma:
        regime = "negative" if net_gex < 0 else "positive"
        try:
            adv = float(adv_shares) if adv_shares is not None else None
        except (TypeError, ValueError):
            adv = None
        if adv is not None and adv > 0 and s > 0:
            gib_pct = (net_gex / (s * s * 0.01 * adv)) * 100.0
    return {
        "call_wall": call_wall,
        "put_wall": put_wall,
        "max_oi_strike": max_oi_strike,
        "net_gex": round(net_gex, 1) if have_gamma else None,
        "regime": regime,
        "gamma_imbalance_pct": gib_pct,
        "adv_shares": adv if have_gamma and gib_pct is not None else None,
    }


def _nonnegative_reading(value):
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def unusual_rows_from_chain(
    chain: dict[str, Any],
    vol_marks: dict[str, tuple[float, float]] | None = None,
    mid_marks: dict[str, float] | None = None,
    now: float | None = None,
    observations: dict | None = None,
) -> tuple[list[list], dict[str, dict[str, Any]]]:
    """Public chain dict → (cvserver-shaped unusual list-rows, quote-truth extras).

    extras[ckey] = {premium_true, side, nbbo_side, signed_side, sign_method,
    bias, mid, last, vol_delta, velocity_per_min}. Malformed contracts are
    dropped, never raised. Rows sorted vol_oi desc so the strongest
    positioning leads even before scoring.

    Saved per-name observations retain receipt-window changes separately
    from source-timed volume rates. Legacy receipt marks cannot establish
    arrival rates. Quote signing requires fresh, ordered actual quote/trade
    times; prior mids cannot look ahead or survive a long rotation as fresh.
    """
    if not isinstance(chain, dict):
        return [], {}
    under = str(chain.get("ticker") or "").upper()
    spot_f = _nonnegative_reading(chain.get("spot")) or None
    now = time.time() if now is None else now
    marks = vol_marks if vol_marks is not None else {}
    observations = observations or {}
    out: list[tuple[float, list]] = []
    extras: dict[str, dict[str, Any]] = {}
    for c in unique_contracts(chain.get("contracts", []))[0]:
        try:
            if not isinstance(c, dict):
                continue
            volume = _nonnegative_reading(c.get("volume"))
            if volume is None:
                continue
            vol = int(volume)
            oi_value = _nonnegative_reading(c.get("oi"))
            oi = int(oi_value) if oi_value is not None else None
            if vol < MIN_VOL:
                continue
            vol_oi = (vol / oi) if oi is not None and oi > 0 else None
            if (vol_oi is None or vol_oi < MIN_VOL_OI) and vol < BIG_VOL:
                continue
            strike = float(c.get("strike") or 0)
            if not math.isfinite(strike) or strike <= 0:  # D3: no nan/inf strikes
                continue
            typ = str(c.get("type") or "").lower()
            ctype = "call" if typ.startswith("c") else "put" if typ.startswith("p") else None
            if ctype is None:
                continue
            exp = str(c.get("expiry") or "")[:10]
            if not exp:
                continue
            iv_f = _nonnegative_reading(c.get("iv")) or None
            _delta = c.get("delta")
            if isinstance(_delta, float) and not math.isfinite(_delta):
                _delta = None
            row = [
                under,
                str(c.get("osi") or ""),
                ctype,
                strike,
                exp,
                vol,
                oi,
                iv_f,
                _delta,
                spot_f,
            ]
            out.append((vol_oi if vol_oi is not None else -1, row))
            # ── quote truth (paid feed only) ──
            bid = c.get("bid")
            ask = c.get("ask")
            last = c.get("last")
            mid_f = _contract_mid(c)
            px = mid_f
            if px is None:
                try:
                    px = float(last) if last is not None else None
                except (TypeError, ValueError):
                    px = None
            # D3: quote fields must be finite — a nan/inf float breaks
            # strict JSON downstream; unknown is None, never fiction.
            if isinstance(px, float) and not math.isfinite(px):
                px = None
            if isinstance(mid_f, float) and not math.isfinite(mid_f):
                mid_f = None
            _last = last
            if isinstance(_last, float) and not math.isfinite(_last):
                _last = None
            premium_true = vol * 100 * px if px and px > 0 else None
            previous_quote = observations.get(str(c.get("osi") or ""), {})
            previous_quote_time = timestamp(previous_quote.get("quote_timestamp"))
            current_quote_time = quote_time(c)
            quote_ordered = (not previous_quote or (
                timestamp(previous_quote.get("received_at")) is not None
                and timestamp(previous_quote.get("received_at")) < now
                and not previous_quote.get("uncertain")
                and (previous_quote_time is None or current_quote_time is not None
                     and current_quote_time > previous_quote_time)))
            quote_eligible = eligible_quote(c, now) and quote_ordered
            side = nbbo_side(last, bid, ask) if quote_eligible else None
            # Relative spread (C4 execution input): spread/mid, None without
            # a valid two-sided quote. Wide-spread + aggressive (Glosten–
            # Milgrom adverse selection) reads as informed urgency.
            rel_spread: float | None = None
            try:
                _b, _a = float(bid), float(ask)
                _m = float(mid_f) if mid_f else None
                if _a > _b > 0 and _m and _m > 0:
                    rel_spread = (_a - _b) / _m
            except (TypeError, ValueError):
                rel_spread = None
            if rel_spread is not None and not math.isfinite(rel_spread):
                rel_spread = None
            osi = str(c.get("osi") or "")
            # ── Lee-Ready signing (A2): quote rule on this sweep, tick test
            # on the previous sweep's mid. prev_mid None on first sight →
            # tick honestly degrades to UNKNOWN (never a forced side).
            signed_side: str | None = None
            sign_method: str | None = None
            if osi and quote_eligible:
                previous_quote = observations.get(osi, {})
                previous_time = timestamp(previous_quote.get("quote_timestamp"))
                prev_mid = previous_quote.get("mid") if (previous_time is not None
                    and 0 < now - previous_time <= 60
                    and previous_time < timestamp(c.get("last_timestamp") or c.get("last_event_time"))
                    and session_day(now) == session_day(previous_time)) else None
                try:
                    signed_side, sign_method = _sign_print(last, bid, ask, prev_mid)
                except Exception:
                    signed_side, sign_method = "UNKNOWN", "none"
                if signed_side not in ("ASK", "BID"):
                    signed_side = None
            previous = observations.get(osi)
            if previous is None and osi in marks:
                legacy = marks[osi]
                if isinstance(legacy, (tuple, list)) and len(legacy) == 2:
                    previous = dict(volume=legacy[0], received_at=legacy[1])
            changes = volume_change(c, previous, now)
            extras[ckey_of(under, ctype, strike, exp)] = {
                "premium_true": premium_true,
                "premium_basis": "snapshot_volume_x_quote" if premium_true is not None else None,
                "premium_is_estimate": True,
                "activity_basis": "cumulative_snapshot",
                "side": "FLOW",
                "last_trade_side": signed_side or side,
                "nbbo_side": side,
                "signed_side": signed_side,
                "sign_method": sign_method,
                "bias": None,
                "mid": mid_f,
                "last": _last,
                "rel_spread": rel_spread,
                **changes,
                "volume_data_received_at": now,
            }
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda t: t[0], reverse=True)
    rows = [r for _, r in out[:MAX_ROWS_PER_TICKER]]
    keep = {ckey_of(r[0], r[2], r[3], r[4]) for r in rows}
    extras = {k: v for k, v in extras.items() if k in keep}
    return rows, extras


def merge_slices(
    slices: dict[str, dict],
    now: float | None = None,
    ttl_s: float = SLICE_TTL_S,
    universe: list[str] | None = None,
) -> tuple[list[list], dict[str, dict[str, Any]], dict[str, Any]]:
    """Merge per-ticker slices into (rows, extras, coverage).

    Stale slices (> ttl) are dropped with their extras and counted (honesty:
    the UI can show which names are fresh vs aging instead of one STALE bit).
    """
    now = time.time() if now is None else now
    rows: list[list] = []
    extras: dict[str, dict[str, Any]] = {}
    fresh: list[str] = []
    stale_dropped: list[str] = []
    max_age: float = 0.0
    allowed = set(slices if universe is None else universe)
    for ticker, entry in slices.items():
        if ticker not in allowed:
            continue
        age = now - float(entry.get("ts", 0))
        if age > ttl_s:
            stale_dropped.append(ticker)
            continue
        fresh.append(ticker)
        max_age = max(max_age, age)
        rows.extend(entry.get("rows", []))
        extras.update(entry.get("extras", {}))
    # Deterministic order: day_volume desc (mirrors /scan sort contract).
    with contextlib.suppress(TypeError, IndexError):
        rows.sort(key=lambda r: float(r[5] or 0), reverse=True)
    row_keys = set()
    for r in rows:
        with contextlib.suppress(TypeError, IndexError, ValueError):
            row_keys.add(ckey_of(r[0], r[2], r[3], r[4]))
    extras = {k: v for k, v in extras.items() if k in row_keys}
    coverage = {
        "universe": len(allowed),
        "fresh": len(fresh),
        "stale_dropped": stale_dropped,
        "max_age_s": round(max_age, 1),
    }
    return rows, extras, coverage


# ── I/O ───────────────────────────────────────────────────────────────

_slices: dict[str, dict] = {}   # ticker -> {ts, rows, extras, dealer}
_cursor: int = 0
_attempts: dict[str, dict] = {}
_scan_lock = asyncio.Lock()
_vol_marks: dict[str, tuple[float, float]] = {}  # osi -> (vol, ts)
_mid_marks: dict[str, float] = {}  # osi -> last-seen mid (Lee-Ready tick anchor)
_mid_rings: dict[str, list[float]] = {}  # legacy test helper only
_observation_store = None
_findings_store = None


def _recent_findings_store():
    global _findings_store
    if _findings_store is None:
        from services.scan_findings import ScanFindings
        default = Path(__file__).resolve().parents[1] / "data" / "scan_findings.sqlite3"
        _findings_store = ScanFindings(os.environ.get("FLOWW_PUBLIC_FINDINGS_PATH") or default)
    return _findings_store


def _observations_store():
    global _observation_store
    if _observation_store is None:
        default = Path(__file__).resolve().parents[1] / "data" / "scan_observations.sqlite3"
        _observation_store = SnapshotObservations(os.environ.get("FLOWW_PUBLIC_OBSERVATIONS_PATH") or default)
    return _observation_store


def _reset_state() -> None:
    """Tests only — clear slices + cursor + velocity/mid marks + rings."""
    global _cursor, _observation_store, _findings_store
    from services.scan_findings import ScanFindings
    if _findings_store is not None:
        _findings_store.close()
    _findings_store = ScanFindings(":memory:")
    if _observation_store is not None:
        _observation_store.close()
    _observation_store = SnapshotObservations(":memory:")
    _slices.clear()
    _attempts.clear()
    _cursor = 0
    _vol_marks.clear()
    _mid_marks.clear()
    _mid_rings.clear()


def _contract_mid(c: dict[str, Any]) -> float | None:
    """Finite midpoint backed by a valid two-sided book."""
    try:
        bid, ask = float(c.get("bid")), float(c.get("ask"))
        if not math.isfinite(bid) or not math.isfinite(ask) or not ask >= bid > 0:
            return None
        mid = c.get("mid")
        if mid is None:
            return bid + (ask - bid) / 2
        value = float(mid)
        if math.isfinite(value) and bid <= value <= ask:
            return value
    except (TypeError, ValueError):
        pass
    return None


def _stamp_marks(contracts: list[dict[str, Any]], now: float) -> None:
    """Legacy pure-test helper; production comparison uses per-name persistence."""
    selected, _ = select_observations(contracts, [], now)
    for osi, item in selected.items():
        previous = _vol_marks.get(osi)
        if previous is not None and previous[1] >= now:
            continue
        _vol_marks[osi] = (item["volume"], now)
        if item["mid"] is not None:
            _mid_marks[osi] = item["mid"]
            _mid_rings[osi] = item["mid_ring"]
    # This compatibility helper is never the production all-market cache.
    if len(_vol_marks) > 60:
        for osi in list(_vol_marks)[:-60]:
            _vol_marks.pop(osi, None)
            _mid_marks.pop(osi, None)
            _mid_rings.pop(osi, None)


async def scan_slice(
    tickers: list[str],
    max_expiries: int = 2,
    concurrency: int = 3,
) -> dict[str, dict[str, Any]]:
    """Fetch chains for `tickers` and extract unusual rows + extras + dealer.

    Never raises. Returns {ticker: {"rows", "extras", "dealer"}}. A ticker
    whose chain fails — or whose fan-out the budget refuses (the adapter
    debits acquire_n(2+N) per C8 and returns None on refusal) — maps to
    empty rows (its prior slice is left untouched by the caller so one
    failure can't wipe coverage). This layer performs zero budget
    acquisition itself: scanner-side reserve would double-debit (D2).

    Pack status (D3): "ok" even when the fresh scan finds zero unusual
    rows (the caller then clears obsolete rows); "failed" when no fresh
    read exists (the caller keeps the prior slice with its age).
    """
    from services.agent.contracts import instant
    from services.public_api_adapter import fetch_chain_from_public_api

    out: dict[str, dict[str, Any]] = {}
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(t: str) -> None:
        async with sem:
            try:
                chain = await fetch_chain_from_public_api(t, max_expiries=max_expiries)
            except Exception as e:
                log.warning("public scanner slice fail %s: %s", t, e)
                out[t] = {"rows": [], "extras": {}, "dealer": None, "status": "failed"}
                return
            if not chain:
                out[t] = {"rows": [], "extras": {}, "dealer": None, "status": "failed"}
                return
            received = instant(chain.get("fetched_at"))
            received_ts = datetime.fromisoformat(received).timestamp() if received else None
            if chain.get("stale") or received_ts is None or not -30 <= time.time() - received_ts <= 300:
                out[t] = {"rows": [], "extras": {}, "dealer": None, "status": "failed"}
                return
            now = received_ts
            contracts, contract_conflicts = unique_contracts(chain.get("contracts", []))
            history_status = "available"
            try:
                saved = await asyncio.to_thread(_observations_store().read, t)
                prior = saved["records"] if saved else {}
            except Exception as exc:
                log.warning("Snapshot history read unavailable for %s (%s)", t, type(exc).__name__)
                prior = {}
                history_status = "unavailable"
            rows, extras = unusual_rows_from_chain(chain, now=now, observations=prior)
            try:
                spot = float(chain.get("spot") or 0)
            except (TypeError, ValueError):
                spot = 0
            # Measured ADV unlocks the real ΓIB pct (B2). Cached 6h in
            # market_bars; fail-open to regime-only on any miss.
            adv: float | None = None
            if _get_adv is not None:
                try:
                    adv = await _get_adv(t)
                except Exception as e:
                    log.debug("public scanner ADV miss %s: %s", t, e)
            dealer = dealer_context(contracts, spot, adv_shares=adv)
            observations, history_capped = select_observations(contracts, [row[1] for row in rows], now, prior)
            try:
                saved_status = await asyncio.to_thread(_observations_store().write, t, now, observations)
                if saved_status not in ("saved", "unchanged"):
                    history_status = saved_status
            except Exception as exc:
                log.warning("Snapshot history save unavailable for %s (%s)", t, type(exc).__name__)
                history_status = "unavailable"
            dealer["roll_spread"] = _roll_pooled_for({osi: value["mid_ring"] for osi, value in observations.items()})
            out[t] = {"rows": rows, "extras": extras, "dealer": dealer, "status": "ok", "received_ts": received_ts,
                      "event_time": instant(chain.get("event_time")),
                      "expiries_checked": len(chain.get("expiries") or []),
                      "rows_capped": len(rows) >= MAX_ROWS_PER_TICKER,
                      "history_status": history_status, "history_capped": history_capped,
                      "history_contracts": len(observations), "contract_conflicts": contract_conflicts}

    await asyncio.gather(*(_one(t) for t in tickers))
    return out


async def scan_next(
    slice_size: int = 8,
    max_expiries: int = 2,
    universe: list[str] | None = None,
) -> dict[str, Any]:
    """Scan the next rotating slice and return the merged universe view.

    Single-flight (concurrent callers share one sweep). The cursor advances
    exactly once per sweep — a slow sweep never double-spends budget.

    Budget-adaptive (B4): the slice is trimmed to what the bucket can
    afford this tick (one ticker minimum or BudgetExhausted). Skipped
    tickers keep their prior slices and wait for the next rotation —
    coverage degrades gracefully instead of stampeding upstream.
    """
    global _cursor
    catalog = None
    if universe is None and not os.environ.get("FLOWW_PUBLIC_UNIVERSE", "").strip():
        from services.market_catalog import get_catalog
        catalog = await get_catalog()
    uni = list(dict.fromkeys(get_universe() if universe is None else universe))
    async with _scan_lock:
        from services.public_budget import BudgetExhausted
        from services.public_budget import budget as pub_budget

        await pub_budget.check_request_allowed("api.public.com")
        started = time.monotonic()
        per_ticker = chain_cost(max_expiries)
        try:
            affordable = max(0, int(await pub_budget.peek_available() // per_ticker))
        except Exception:
            affordable = slice_size
        if affordable <= 0:
            # Unaffordable: raise WITHOUT moving the cursor, or the
            # skipped rotation starves the slice it consumed (D2).
            raise BudgetExhausted(retry_after=5, reason="slice-unaffordable")
        # D2: advance the cursor only by tickers actually scanned. The
        # trimmed tail keeps its rotation slot for the next sweep.
        take = min(slice_size, affordable, len(uni))
        if take < slice_size:
            log.info("public sweep trimmed %d→%d tickers on budget",
                     slice_size, take)
        idx, _cursor = advance_cursor(_cursor, take, len(uni))
        tickers = [uni[i] for i in idx]
        dealer: dict[str, dict[str, Any]] = {
            t: (_slices[t]["dealer"] if isinstance(_slices.get(t), dict) and _slices[t].get("dealer") else None)
            for t in _slices
        }
        if tickers:
            fresh = await scan_slice(tickers, max_expiries=max_expiries)
            for t in tickers:
                pack = fresh.get(t, {"status": "failed"})
                _attempts[t] = {"status": pack.get("status"), "at": time.time(),
                                "findings_saved": _attempts.get(t, {}).get("findings_saved"),
                                "expiries_checked": pack.get("expiries_checked", 0),
                                "history_status": pack.get("history_status", "unavailable"),
                                "history_capped": pack.get("history_capped", False),
                                "contract_conflicts": pack.get("contract_conflicts", 0)}
                # D3: a successful fresh read (even zero rows) replaces the
                # slice — obsolete rows must not pose as current. Only a
                # failed read keeps the prior slice with its age (merge
                # drops it past TTL and names it in coverage).
                received_ts = pack.get("received_ts")
                if pack.get("status") == "ok" and isinstance(received_ts, (float, int)) and math.isfinite(received_ts):
                    _slices[t] = {"ts": received_ts, "rows": pack["rows"], "event_time": pack.get("event_time"),
                                  "extras": pack["extras"], "dealer": pack["dealer"],
                                  "rows_capped": pack.get("rows_capped", False)}
                    dealer[t] = pack["dealer"]
                    try:
                        await asyncio.to_thread(_recent_findings_store().save, t, received_ts, pack["rows"])
                        _attempts[t]["findings_saved"] = True
                    except Exception as exc:
                        _attempts[t]["findings_saved"] = False
                        log.warning("Dated scan findings unavailable (%s)", type(exc).__name__)
        # Removed symbols must not remain in rows or count as scanned.
        for old in set(_slices) - set(uni):
            _slices.pop(old, None)
        for old in set(_attempts) - set(uni):
            _attempts.pop(old, None)
        rows, extras, coverage = merge_slices(_slices, universe=uni)
        # A full provider pass can contain thousands of names. Keep each
        # expired name's last-check time, not its discarded contract payload.
        for expired in coverage["stale_dropped"]:
            _slices[expired] = {"ts": _slices[expired]["ts"], "rows": [],
                                "extras": {}, "dealer": None,
                                "event_time": _slices[expired].get("event_time")}
        duration = max(0, time.monotonic() - started)
        try:
            pause = max(0.1, float(os.environ.get("FLOWW_PUBLIC_SWEEP_RTH_S", "1")))
        except ValueError:
            pause = 1.0
        coverage.update(
            source="public-instruments" if catalog is not None else "custom-universe",
            catalog_stale=bool(catalog and catalog["stale"]),
            catalog_available=bool(catalog["complete_provider_catalog"]) if catalog is not None else True,
            attempted=len(_attempts), never_scanned=max(0, len(uni) - len(_attempts)),
            latest_failed=sum(a["status"] != "ok" for a in _attempts.values()),
            expiries_per_ticker=max_expiries, rows_per_ticker_cap=MAX_ROWS_PER_TICKER,
            rows_capped=any(v.get("rows_capped") for v in _slices.values()),
            fresh_window_seconds=SLICE_TTL_S, checked_at=time.time(),
            estimated_pass_seconds=round(math.ceil(len(uni) / len(tickers)) * (duration + pause)) if tickers else None,
            complete_realtime_market=False,
            history_contract_limit=60,
            history_unavailable=sum(a.get("history_status") != "available" for a in _attempts.values()),
            history_capped=sum(bool(a.get("history_capped")) for a in _attempts.values()),
            arrival_rates_require_source_time=True,
            conflicting_contracts_excluded=sum(a.get("contract_conflicts", 0) for a in _attempts.values()),
        )
        # Dealer context only for tickers actually in the merged view —
        # a dropped stale slice must not keep contributing regime reads.
        fresh_unders = {r[0] for r in rows if r}
        dealer = {t: d for t, d in dealer.items() if d and t in fresh_unders}
        try:
            recent_findings = await asyncio.to_thread(_recent_findings_store().recent, tickers=uni)
            findings_status = "partial" if any(a.get("findings_saved") is False for a in _attempts.values()) else "available"
        except Exception:
            recent_findings, findings_status = [], "unavailable"
        return {
            "columns": SCAN_COLUMNS,
            "rows": rows,
            "count": len(rows),
            "quote_truth": extras,
            "dealer": dealer,
            "coverage": coverage,
            "tickers": sorted(uni),
            "recent_findings": recent_findings,
            "findings_status": findings_status,
        }


async def sweep_once(
    slice_size: int = 8,
    max_expiries: int = 2,
) -> dict[str, Any] | None:
    """One background sweep: budget-gated scan_next + baseline + alerts.

    The always-on path behind the server sweep loop — the SAME pipeline the
    HTTP scan routes feed, so alerts fire and persist with no tabs open.
    Never raises: budget exhaustion skips cleanly (loop backs off on the
    next tick), pipeline failures log and return the view anyway.
    """
    from services.public_budget import BudgetExhausted

    try:
        view = await scan_next(slice_size=slice_size, max_expiries=max_expiries)
    except BudgetExhausted as e:
        log.info("public sweep skipped (retry in ~%ss)", e.retry_after)
        return None
    try:
        from routes.flowseeker import _record_scan_baseline, _run_institutional_alerts

        await _record_scan_baseline(view["rows"])
        await _run_institutional_alerts(
            view["rows"],
            extras=view.get("quote_truth"),
            dealer=view.get("dealer"),
        )
    except Exception as e:
        log.warning("public sweep pipeline failed (non-fatal): %s", e)
    return view
