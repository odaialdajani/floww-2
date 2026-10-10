"""B02 capability census: requested/observed coverage, no new persistence."""
from __future__ import annotations


def census(capability_ids: list[str], status_by_id: dict) -> dict:
    """Count dispositions; unknown status stays unknown, never assumed."""
    by_status: dict[str, int] = {}
    for cid in capability_ids or []:
        status = (status_by_id or {}).get(cid, "unknown")
        by_status[status] = by_status.get(status, 0) + 1
    return {"total": len(capability_ids or []), "by_status": by_status}
