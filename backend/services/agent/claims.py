"""Claim store (plan v3 L10). Every verdict is a machine-readable claim.

Mongo agent_claims with Date fields. Noise floor = k x realised vol,
stored on the claim. Resolver + calibration land in W5a; writing +
path recording start in W2 so history exists to grade later.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
STATUSES = ("open", "win", "loss", "neither", "unresolvable", "malformed")


def new_claim(
    *,
    ticker: str,
    horizon: str,
    direction: str,
    spot_at_claim: float | None = None,
    trigger_level: float | None = None,
    target_zone: Any = None,
    invalidation_level: float | None = None,
    confidence: float | None = None,
    det_score: float | None = None,
    model_view: str | None = None,
    disagreement: bool = False,
    weights_version: str = "v1",
    scorer_version: str = "v1",
    resolver_version: str = "v1",
    model_id: str | None = None,
    ledger_hash: str | None = None,
    proposal_id: str | None = None,
    thread_id: str | None = None,
    chain_asof: str | None = None,
    venue: str = "paper",
) -> dict[str, Any]:
    now = datetime.now(ET)
    noise_floor = _noise_floor(ticker, spot_at_claim)
    return {
        "claim_id": str(uuid.uuid4()),
        "thread_id": thread_id,
        "ticker": (ticker or "").upper(),
        "horizon": (horizon or "all").lower(),
        "venue": venue,
        "made_at": now,
        "chain_asof": chain_asof,
        "spot_at_claim": spot_at_claim,
        "direction": direction,
        "trigger_level": trigger_level,
        "target_zone": target_zone,
        "invalidation_level": invalidation_level,
        "confidence": confidence,
        "det_score": det_score,
        "model_view": model_view,
        "disagreement": bool(disagreement),
        "weights_version": weights_version,
        "scorer_version": scorer_version,
        "resolver_version": resolver_version,
        "model_id": model_id,
        "ledger_hash": ledger_hash,
        "proposal_id": proposal_id,
        "noise_floor": noise_floor,
        "status": "open",
    }


def _noise_floor(ticker: str, spot: float | None) -> float | None:
    try:
        from services.realized_volatility import compute_realized_volatility

        rv = compute_realized_volatility(ticker)
        if isinstance(rv, dict):
            v = rv.get("realized_vol") or rv.get("rv") or 0
        else:
            v = float(rv or 0)
        if spot and v:
            return round(float(spot) * float(v) * 0.5, 2)
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("noise floor unavailable for %s: %s", ticker, e)
    return None


def save_claim(claim: dict[str, Any], db=None) -> dict[str, Any]:
    if db is None:
        return claim
    with contextlib.suppress(Exception):
        db["agent_claims"].insert_one(dict(claim))
    return claim
