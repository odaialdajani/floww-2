"""Per-contract Lee-Ready signing (Agent A1, institutional loop).

R10 (Lee & Ready 1991) + R9 (Hu 2014) justification: every print gets a
signed aggressor side from NBBO truth — quote rule first, tick test as
fallback. Unknown stays UNKNOWN (Law 2): crossed/locked quotes,
mid-prints with no lag, zero-ticks, and degenerate inputs never force
a side.

Snapshot-data adaptation (documented, not hidden): chain snapshots carry
no previous *trade* price, so the tick fallback compares current ``last``
against the ``prev_mid`` lag anchor (mid drift across sweeps, threaded by
Agent B's feed adapters). This mixes anchors by necessity — callers that
need print-exact Lee-Ready must supply per-trade lags, not sweep mids.

Pure functions only — no network.

Side vocabulary here is the NBBO aggressor (ASK = buyer lifted the ask,
BID = seller hit the bid). Mapping to engine BUY/SELL/FLOW is A2's hook
proposal, not this module.
"""

from __future__ import annotations


def _finite(x: object) -> float | None:
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def _valid_quote(bid: float | None, ask: float | None) -> tuple[float, float] | None:
    b, a = _finite(bid), _finite(ask)
    if b is None or a is None or b <= 0 or a <= b:
        return None
    return b, a


def sign_print(
    last: float | None,
    bid: float | None,
    ask: float | None,
    prev_mid: float | None = None,
) -> tuple[str, str]:
    """Sign one print. Returns (side, method).

    side in {ASK, BID, UNKNOWN}; method in {quote, tick, none}.
    Quote rule: last strictly above/below the contemporaneous mid.
    Tick fallback: last vs prev_mid lag anchor (uptick -> ASK, downtick ->
    BID, zero-tick -> UNKNOWN). Anything degenerate -> (UNKNOWN, none).
    """
    px = _finite(last)
    if px is None or px <= 0:
        return "UNKNOWN", "none"
    quote = _valid_quote(bid, ask)
    if quote is not None:
        mid = (quote[0] + quote[1]) / 2.0
        if px > mid:
            return "ASK", "quote"
        if px < mid:
            return "BID", "quote"
        # mid-print: fall through to tick test
    prev = _finite(prev_mid)
    if prev is None or prev <= 0:
        return "UNKNOWN", "none"
    if px > prev:
        return "ASK", "tick"
    if px < prev:
        return "BID", "tick"
    return "UNKNOWN", "none"


def sign_snapshot(rows: list[dict]) -> dict[str, int]:
    """Annotate rows in place with signed_side + sign_method.

    Accepts last/bid/ask (+prev_mid) per row. Returns side counts.
    """
    counts = {"ASK": 0, "BID": 0, "UNKNOWN": 0}
    for r in rows or []:
        side, method = sign_print(
            r.get("last"), r.get("bid"), r.get("ask"), r.get("prev_mid")
        )
        r["signed_side"] = side
        r["sign_method"] = method
        counts[side] += 1
    return counts


def aggressor_omega(rows: list[dict]) -> float | None:
    """Signed-premium share OMEGA = (buy - sell) / (buy + sell), in [-1, 1].

    Prefers premium_truth when present, else premium. UNKNOWN-side rows
    are excluded from both legs. None when no signed premium exists.
    """
    buy = sell = 0.0
    for r in rows or []:
        side = r.get("signed_side")
        if side not in ("ASK", "BID"):
            continue
        prem = _finite(r.get("premium_truth", r.get("premium")))
        if prem is None or prem <= 0:
            continue
        if side == "ASK":
            buy += prem
        else:
            sell += prem
    total = buy + sell
    if total <= 0:
        return None
    return (buy - sell) / total
