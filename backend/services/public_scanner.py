"""
backend/services/public_scanner.py

Public-backed market-wide unusual-flow scanner (paid Advanced API).

Why this exists: `/scan` rides ONE cvserver `screen` (20 upstream calls/hour,
top-300 by raw day_volume). On a busy day mega-cap churn (SPY/QQQ/NVDA/SPX)
fills all 300 slots — mid-cap institutional building (SNDK-type: 3-8k
contracts laddered across strikes, each line score 70-85) never appears, and
the hourly budget leaves the scanner STALE most of each hour.

This scanner walks a UNIVERSE (index ETFs + megas + high-beta mid-caps,
overridable via FLOWW_PUBLIC_UNIVERSE) through the paid Public chains on a
rotating cursor: each call scans the next SLICE of tickers, merges into a TTL
cache, and returns the full-universe view. Per-call upstream cost is bounded
(slice × (2 + expiries) calls against the 60/min Public budget); full
coverage refreshes every few minutes with no hourly cap and no STALE gaps —
every slice carries its own age stamp.

Two payloads come back per sweep, both from the SAME chains (zero extra
upstream calls):

  rows   — cvserver-shaped unusual list-rows (columns [underlying_ticker,
           ticker, contract_type, strike_price, expiration_date, day_volume,
           open_interest, implied_volatility, delta, underlying_price]) so
           flow_alerts.norm_rows / eval_institutional and the frontend
           mkScanRow consume them unchanged.
  extras — quote-truth per contract keyed by ckey: NBBO side (last vs mid),
           Lee-Ready signed_side/sign_method (A2: quote rule + tick test on
           the previous sweep's mid), true premium (mid×vol×100, never a BS
           estimate), per-contract volume velocity (contracts/min since the
           previous sweep — arrival intensity is the institutional urgency
           read), mid/last.
  dealer — per-ticker dealer positioning from real gamma×OI: call/put walls,
           max-OI strike, net dealer gamma + regime. The context an
           institutional alert needs, computed from data already in hand.

Pure helpers (advance_cursor, unusual_rows_from_chain, merge_slices,
nbbo_side, dealer_context) are unit-testable without network; I/O lives in
scan_slice().
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import time
from typing import Any

from services.flow_signing import sign_print as _sign_print
from services.roll_spread import push_capped as _push_capped
from services.roll_spread import roll_pooled_for as _roll_pooled_for

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
    else the curated default. Env override lets the desk reshape coverage
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
    return out or list(UNIVERSE)


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
SLICE_TTL_S = 600.0

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


def unusual_rows_from_chain(
    chain: dict[str, Any],
    vol_marks: dict[str, tuple[float, float]] | None = None,
    mid_marks: dict[str, float] | None = None,
    now: float | None = None,
) -> tuple[list[list], dict[str, dict[str, Any]]]:
    """Public chain dict → (cvserver-shaped unusual list-rows, quote-truth extras).

    extras[ckey] = {premium_true, side, nbbo_side, signed_side, sign_method,
    bias, mid, last, vol_delta, velocity_per_min}. Malformed contracts are
    dropped, never raised. Rows sorted vol_oi desc so the strongest
    positioning leads even before scoring.

    vol_marks ({osi: (vol, ts)}) turns cumulative day-volume into arrival
    intensity: vol_delta = new contracts since the mark; velocity_per_min =
    delta / elapsed minutes (None on first sight or clock anomalies — honest
    unknown, never a fabricated zero that would read as "dead flow").
    mid_marks ({osi: mid}) feeds the Lee-Ready tick fallback: the previous
    sweep's mid is the lag anchor (snapshot-data adaptation — prev trade
    price unavailable in chain snapshots; see flow_signing.sign_print).
    """
    if not isinstance(chain, dict):
        return [], {}
    under = str(chain.get("ticker") or "").upper()
    spot = chain.get("spot") or 0
    try:
        spot_f = float(spot) or 0
    except (TypeError, ValueError):
        spot_f = 0
    if not math.isfinite(spot_f):  # D3: float("nan") is truthy — never emit it
        spot_f = 0
    now = time.time() if now is None else now
    marks = vol_marks if vol_marks is not None else {}
    mids = mid_marks if mid_marks is not None else {}
    out: list[tuple[float, list]] = []
    extras: dict[str, dict[str, Any]] = {}
    for c in chain.get("contracts", []) or []:
        try:
            if not isinstance(c, dict):
                continue
            vol = int(float(c.get("volume") or 0))
            oi = int(float(c.get("oi") or 0))
            if vol < MIN_VOL:
                continue
            vol_oi = (vol / oi) if oi > 0 else float(vol)
            if vol_oi < MIN_VOL_OI and vol < BIG_VOL:
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
            iv = c.get("iv") or 0
            try:
                iv_f = float(iv)
            except (TypeError, ValueError):
                iv_f = 0
            if not math.isfinite(iv_f):  # D3: never emit nan/inf IV
                iv_f = 0
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
            out.append((vol_oi, row))
            # ── quote truth (paid feed only) ──
            bid = c.get("bid")
            ask = c.get("ask")
            last = c.get("last")
            mid = c.get("mid")
            try:
                mid_f = float(mid) if mid is not None else None
                if (mid_f is None and bid is not None and ask is not None
                        and float(ask) > float(bid) > 0):
                    mid_f = (float(bid) + float(ask)) / 2
            except (TypeError, ValueError):
                mid_f = None
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
            side = nbbo_side(last, bid, ask)
            s, bias = side_bias(ctype, side)
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
            if osi:
                prev_mid = mids.get(osi)
                try:
                    signed_side, sign_method = _sign_print(last, bid, ask, prev_mid)
                except Exception:
                    signed_side, sign_method = "UNKNOWN", "none"
                if signed_side not in ("ASK", "BID"):
                    signed_side = None
            # ── velocity from marks ──
            vol_delta: float | None = None
            velocity: float | None = None
            if osi:
                prev = marks.get(osi)
                if prev is not None:
                    prev_vol, prev_ts = prev
                    dt_min = (now - prev_ts) / 60.0
                    if vol >= prev_vol:
                        vol_delta = float(vol - prev_vol)
                    else:
                        vol_delta = float(vol)  # session rollover: full figure is fresh
                    if dt_min > 0:
                        velocity = vol_delta / dt_min
            extras[ckey_of(under, ctype, strike, exp)] = {
                "premium_true": premium_true,
                "side": s if side else "FLOW",
                "nbbo_side": side,
                "signed_side": signed_side,
                "sign_method": sign_method,
                "bias": bias,
                "mid": mid_f,
                "last": _last,
                "rel_spread": rel_spread,
                "vol_delta": vol_delta,
                "velocity_per_min": velocity,
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
    for ticker, entry in slices.items():
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
        "universe": len(get_universe()),
        "fresh": len(fresh),
        "stale_dropped": stale_dropped,
        "max_age_s": round(max_age, 1),
    }
    return rows, extras, coverage


# ── I/O ───────────────────────────────────────────────────────────────

_slices: dict[str, dict] = {}   # ticker -> {ts, rows, extras, dealer}
_cursor: int = 0
_scan_lock = asyncio.Lock()
_vol_marks: dict[str, tuple[float, float]] = {}  # osi -> (vol, ts)
_mid_marks: dict[str, float] = {}  # osi -> last-seen mid (Lee-Ready tick anchor)
_mid_rings: dict[str, list[float]] = {}  # osi -> capped mid history (Roll cost)


def _reset_state() -> None:
    """Tests only — clear slices + cursor + velocity/mid marks + rings."""
    global _cursor
    _slices.clear()
    _cursor = 0
    _vol_marks.clear()
    _mid_marks.clear()
    _mid_rings.clear()


def _contract_mid(c: dict[str, Any]) -> float | None:
    """Best mid for one chain contract: vendor mid, else (bid+ask)/2."""
    try:
        mid = c.get("mid")
        if mid is not None and float(mid) > 0:
            return float(mid)
        bid, ask = float(c.get("bid")), float(c.get("ask"))
        if ask > bid > 0:
            return (bid + ask) / 2
    except (TypeError, ValueError):
        pass
    return None


def _stamp_marks(contracts: list[dict[str, Any]], now: float) -> None:
    """Record current cumulative volumes + mids for the next sweep.

    Volumes feed velocity math; mids feed the Lee-Ready tick fallback and
    the per-contract Roll rings (bounded at 60 mids/contract).
    Bounded: entries for contracts never seen again are pruned when the
    maps grow past 20k keys (long-lived-process guard)."""
    for c in contracts or []:
        try:
            if not isinstance(c, dict):
                continue
            osi = str(c.get("osi") or "")
            if not osi:
                continue
            _vol_marks[osi] = (float(c.get("volume") or 0), now)
            mid = _contract_mid(c)
            if mid is not None:
                _mid_marks[osi] = mid
                _mid_rings[osi] = _push_capped(_mid_rings.get(osi), mid, cap=60)
        except (TypeError, ValueError):
            continue
    if len(_vol_marks) > 20000:
        # Drop oldest by timestamp (marks are (vol, ts) tuples).
        for osi in sorted(_vol_marks, key=lambda k: _vol_marks[k][1])[: len(_vol_marks) - 20000]:
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
    from services.public_api_adapter import fetch_chain_from_public_api

    out: dict[str, dict[str, Any]] = {}
    sem = asyncio.Semaphore(max(1, concurrency))
    now = time.time()

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
            contracts = chain.get("contracts", []) or []
            rows, extras = unusual_rows_from_chain(
                chain, vol_marks=_vol_marks, mid_marks=_mid_marks, now=now
            )
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
            _stamp_marks(contracts, now)
            # Roll read over this ticker's contracts (pooled bucket).
            # Building state until ~30 deltas — an honest "warming up",
            # never a premature number.
            tick_osis = {str(c.get("osi") or "") for c in contracts
                         if isinstance(c, dict) and c.get("osi")}
            tick_rings = {o: _mid_rings[o] for o in tick_osis if o in _mid_rings}
            dealer["roll_spread"] = _roll_pooled_for(tick_rings)
            out[t] = {"rows": rows, "extras": extras, "dealer": dealer, "status": "ok"}

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
    uni = universe or get_universe()
    async with _scan_lock:
        from services.public_budget import BudgetExhausted
        from services.public_budget import budget as pub_budget

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
            now = time.time()
            for t, pack in fresh.items():
                # D3: a successful fresh read (even zero rows) replaces the
                # slice — obsolete rows must not pose as current. Only a
                # failed read keeps the prior slice with its age (merge
                # drops it past TTL and names it in coverage).
                if pack.get("status") == "ok":
                    _slices[t] = {"ts": now, "rows": pack["rows"],
                                  "extras": pack["extras"], "dealer": pack["dealer"]}
                    dealer[t] = pack["dealer"]
                elif pack["rows"]:
                    _slices[t] = {"ts": now, **pack}
                    dealer[t] = pack["dealer"]
        rows, extras, coverage = merge_slices(_slices)
        # Dealer context only for tickers actually in the merged view —
        # a dropped stale slice must not keep contributing regime reads.
        fresh_unders = {r[0] for r in rows if r}
        dealer = {t: d for t, d in dealer.items() if d and t in fresh_unders}
        return {
            "columns": SCAN_COLUMNS,
            "rows": rows,
            "count": len(rows),
            "quote_truth": extras,
            "dealer": dealer,
            "coverage": coverage,
            "tickers": sorted(_slices.keys()),
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
    from services.public_budget import budget as pub_budget

    try:
        await pub_budget.acquire("api.public.com")
    except BudgetExhausted as e:
        log.info(
            "public sweep skipped — budget spent (retry in ~%ss)", e.retry_after)
        return None
    try:
        view = await scan_next(slice_size=slice_size, max_expiries=max_expiries)
    except BudgetExhausted as e:
        log.info("public sweep skipped — slice unaffordable (retry in ~%ss)",
                 e.retry_after)
        return None
    finally:
        pub_budget.release()
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
