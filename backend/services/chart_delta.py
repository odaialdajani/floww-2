"""B22 CVD/delta/footprint: actual classified sizes, session resets."""
from __future__ import annotations


def session_cvd(bars: list[dict]):
    """Running buy-minus-sell; period opens at zero; missing bar => no candle."""
    running = 0
    out = []
    for b in (bars or []):
        if b is None or b.get("buy") is None or b.get("sell") is None:
            continue
        buy, sell = b["buy"], b["sell"]
        if not all(isinstance(v, (int, float)) for v in (buy, sell)):
            continue
        prev = running
        running += buy - sell
        out.append({"open": prev, "close": running, "delta": buy - sell,
                    "unclassified": b.get("unclassified", 0)})
    return out
