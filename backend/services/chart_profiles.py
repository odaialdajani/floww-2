"""B23 profiles/TPO: exact vs approximate, POC ties down, VA up, no future."""
from __future__ import annotations


def poc(rows: list[dict]):
    """Point of control: max volume; ties resolve downward (lower price)."""
    if not rows:
        return None
    best = max(r.get("volume", 0) for r in rows)
    cands = [r for r in rows if r.get("volume", 0) == best]
    return min(cands, key=lambda r: r["price"])


def value_area(rows: list[dict], pct=0.70):
    """Expand from POC; equal adjacent-area expansion upward; stop on sparse gaps."""
    if not rows:
        return {"status": "unavailable"}
    ordered = sorted(rows, key=lambda r: r["price"])
    total = sum(r.get("volume", 0) for r in ordered)
    if total <= 0:
        return {"status": "unavailable"}
    target = total * pct
    center = ordered.index(poc(ordered))
    lo = hi = center
    acc = ordered[center].get("volume", 0)
    while acc < target:
        up = ordered[hi + 1].get("volume", 0) if hi + 1 < len(ordered) else None
        dn = ordered[lo - 1].get("volume", 0) if lo - 1 >= 0 else None
        if up is None and dn is None:
            break
        if up is None:
            lo -= 1
            acc += dn
        elif dn is None or up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
        if up == 0 and dn == 0:
            break
    return {"status": "ok", "low": ordered[lo]["price"], "high": ordered[hi]["price"],
            "attained": acc / total}
