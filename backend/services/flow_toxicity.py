"""Bar-VPIN toxicity + O/S venue + gate/slippage helpers (Agent A3).

Adaptations of Easley–López de Prado–O'Hara VPIN (2012, JFE) and the
Johnson–So / Roll–Schwartz–Subrahmanyam O/S venue literature to
C13 bars-lists ([{t,o,h,l,c,v}]) — documented, never silent:

- VPIN needs trade direction; bars carry none. Each bar's volume is
  signed by a tick rule on closes (bar's own o→c for the first bar,
  then c[i] vs c[i-1]; zero-ticks inherit the last nonzero move, split
  50/50 only when no history exists). This is coarser than trade-VPIN:
  treat the output as a toxicity *proxy*, never a print-exact read.
- Buckets are equal-volume (total/n_buckets), bars split proportionally
  across bucket boundaries (standard bulk classification).

Pure functions on injected data — no network. Thresholds are required
arguments (no desk-tunable default is smuggled in; see toxicity_gate).
"""

from __future__ import annotations


def _signed_volumes(bars: list[dict] | None) -> list[tuple[float, float]]:
    """[(buy_vol, sell_vol)] per bar via the close-tick rule."""
    out: list[tuple[float, float]] = []
    prev_c: float | None = None
    last_sign = 0
    for b in bars or []:
        try:
            c = float(b["c"])
            v = float(b.get("v", 0) or 0)
            o = float(b.get("o", c))
        except (KeyError, TypeError, ValueError):
            continue
        if v <= 0:
            continue
        if prev_c is None:
            move = c - o
        else:
            move = c - prev_c
        if move > 0:
            last_sign = 1
        elif move < 0:
            last_sign = -1
        if last_sign >= 0:
            out.append((v, 0.0))
        else:
            out.append((0.0, v))
        # zero-tick with no history (first bar, o==c): split honestly
        if move == 0 and prev_c is None and c == o:
            out[-1] = (v / 2.0, v / 2.0)
        prev_c = c
    return out


def bucket_imbalance(buy: float, sell: float) -> float | None:
    """|buy - sell| / (buy + sell). None on empty bucket."""
    total = (buy or 0.0) + (sell or 0.0)
    if total <= 0:
        return None
    return abs((buy or 0.0) - (sell or 0.0)) / total


def vpin_from_bars(
    bars: list[dict] | None,
    n_buckets: int = 50,
) -> dict[str, object]:
    """Bar-VPIN proxy: mean bucket imbalance over equal-volume buckets.

    Returns {vpin|None, buckets_filled, buy, sell, method: "bar-tick-rule"}.
    None (not 0.0) when fewer than 2 buckets fill — thin history is
    unknown toxicity, never "clean".
    """
    if n_buckets < 2:
        return {"vpin": None, "buckets_filled": 0, "buy": 0.0, "sell": 0.0,
                "method": "bar-tick-rule"}
    signed = _signed_volumes(bars)
    total = sum(b + s for b, s in signed)
    if total <= 0:
        return {"vpin": None, "buckets_filled": 0, "buy": 0.0, "sell": 0.0,
                "method": "bar-tick-rule"}
    if len(signed) < n_buckets:
        # Fewer bars than buckets: each bucket would be a sliver of one bar
        # (e.g. 2 bars into 50 buckets). Unknown toxicity, never a number.
        return {"vpin": None, "buckets_filled": 0,
                "buy": sum(b for b, _ in signed), "sell": sum(s for _, s in signed),
                "method": "bar-tick-rule"}
    bucket_vol = total / n_buckets
    imbalances: list[float] = []
    buy_tot = sell_tot = 0.0
    cur_buy = cur_sell = 0.0
    for b, s in signed:
        buy_tot += b
        sell_tot += s
        remaining_b, remaining_s = b, s
        while remaining_b + remaining_s > 1e-12:
            room = bucket_vol - (cur_buy + cur_sell)
            take = min(room, remaining_b + remaining_s)
            frac = take / (remaining_b + remaining_s)
            cur_buy += remaining_b * frac
            cur_sell += remaining_s * frac
            remaining_b *= 1.0 - frac
            remaining_s *= 1.0 - frac
            if cur_buy + cur_sell >= bucket_vol - 1e-9:
                imb = bucket_imbalance(cur_buy, cur_sell)
                imbalances.append(imb if imb is not None else 0.0)
                cur_buy = cur_sell = 0.0
    if len(imbalances) < 2:
        return {"vpin": None, "buckets_filled": len(imbalances),
                "buy": buy_tot, "sell": sell_tot, "method": "bar-tick-rule"}
    return {"vpin": sum(imbalances) / len(imbalances),
            "buckets_filled": len(imbalances),
            "buy": buy_tot, "sell": sell_tot, "method": "bar-tick-rule"}


def os_ratio(option_contracts: float | None, share_volume: float | None) -> float | None:
    """Option-to-stock volume: contracts×100 shares ÷ share volume.

    High O/S = informed venue shift (Johnson–So 2012). None without
    share volume; 0.0 for genuinely zero option volume.
    """
    try:
        oc = float(option_contracts or 0)
        sv = float(share_volume) if share_volume is not None else None
    except (TypeError, ValueError):
        return None
    if sv is None or sv <= 0:
        return None
    return (oc * 100.0) / sv


def toxicity_gate(vpin: float | None, threshold: float) -> tuple[str, str]:
    """BLOCK fresh directional size into toxic tape, else ALLOW.

    Threshold is REQUIRED (no smuggled default): calibrate per instrument
    from the VPIN CDF (Easley et al.gate at high quantiles), post the
    chosen value in LEDGER. Unknown VPIN never blocks (ALLOW) — absence
    of evidence is not evidence of toxicity.
    """
    if vpin is None:
        return "ALLOW", "vpin unknown — no gate"
    try:
        v = float(vpin)
        t = float(threshold)
    except (TypeError, ValueError):
        return "ALLOW", "vpin unreadable — no gate"
    if v >= t:
        return "BLOCK", f"vpin {v:.2f} >= {t:.2f}"
    return "ALLOW", f"vpin {v:.2f} < {t:.2f}"


def projected_slippage_bp(kyle_lambda: float | None, notional: float | None) -> float | None:
    """Linear price-impact projection: λ × notional × 1e4 = basis points.

    λ units: fractional price return per $1 notional (Kyle 1985 λ adapted
    to notional). λ itself comes from Agent B's bars fit — this function
    only does the arithmetic, loudly unit-labeled. None without λ.
    """
    try:
        lam = float(kyle_lambda) if kyle_lambda is not None else None
        ntl = float(notional or 0)
    except (TypeError, ValueError):
        return None
    if lam is None:
        return None
    return lam * ntl * 1e4
