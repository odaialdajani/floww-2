"""Pure WallDeskSnapshot.v1 projection from canonical exposure metrics.

This module is intentionally route/server/persistence-free. It consumes the
frozen source-shaped fixture (or the same-shaped live canonical input) and
returns a redacted packet using only:

- domain.exposure_metrics.compute_raw_oi
- domain.exposure_metrics.compute_delta_weighted_oi
- domain.exposure_metrics.compute_volume_gamma

No new Greek engine, no polarity-by-spot-division, no inferred zero-gamma
root, no fake expiry/zero/stale/ticker defaults, and no interpolation.
Missing values stay missing with reason codes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.exposure_metrics import (  # noqa: E402
    FORMULA_VERSION,
    compute_delta_weighted_oi,
    compute_raw_oi,
    compute_volume_gamma,
)
from tests.fixtures.wall_desk_fixture_v1 import (  # noqa: E402
    EXPECTED_PACKET_T0,
    EXPECTED_WINDOW_T0_T1,
    FIXTURE_VERSION,
    SOURCE_OBSERVATION_T0,
    SOURCE_OBSERVATION_T1,
    SPOT,
)

SNAPSHOT_VERSION = "WallDeskSnapshot.v1"


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def project_packet(observation: dict[str, Any], snapshot_id: str) -> dict[str, Any]:
    """Project one source-shaped observation into a redacted desk packet."""
    contracts = observation.get("contracts") or []
    spot = _finite(observation.get("spot")) or SPOT
    raw = compute_raw_oi(contracts, spot)
    adj = compute_delta_weighted_oi(contracts, spot)
    vol = compute_volume_gamma(contracts, spot)

    missing_delta = sorted(
        str(c.get("osi"))
        for c in contracts
        if isinstance(c, dict) and c.get("delta") is None
    )
    stale = sorted(
        str(c.get("osi"))
        for c in contracts
        if isinstance(c, dict) and c.get("quote_status") == "stale"
    )
    reasons = sorted(
        {*(["DELTA_MISSING"] if missing_delta else []), *(["QUOTE_STALE"] if stale else [])}
    )
    expiries = sorted({str(c.get("expiry")) for c in contracts if c.get("expiry")})

    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "formula_version": FORMULA_VERSION,
        "snapshot_id": snapshot_id,
        "ticker": observation.get("ticker"),
        "spot": spot,
        "asof": observation.get("asof"),
        "source_received_at": observation.get("source_received_at"),
        "data_source": observation.get("data_source"),
        "wall_id": "K100",
        "units": "USD/1% move",
        "raw_gross": raw.gross,
        "raw_net": raw.net,
        "raw_usable": raw.usable,
        "raw_missing_oi": raw.missing_oi,
        "raw_invalid": raw.invalid,
        "delta_gross": adj.gross,
        "delta_net": adj.net,
        "delta_usable": adj.usable,
        "delta_missing": adj.missing_delta,
        "delta_invalid": adj.invalid,
        "volume_gross_like": vol.gross,
        "volume_net": vol.net,
        "volume_usable": vol.usable,
        "volume_missing": vol.missing_oi,
        "volume_invalid": vol.invalid,
        "coverage": {
            "expiries": expiries,
            "stale": stale,
            "missing_delta": missing_delta,
        },
        "reason_codes": reasons,
    }


def project_window(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Window delta-volume activity between comparable cumulative observations."""
    start_map = {
        str(c.get("osi")): c for c in (first.get("contracts") or []) if isinstance(c, dict)
    }
    end_map = {
        str(c.get("osi")): c for c in (second.get("contracts") or []) if isinstance(c, dict)
    }
    spot = _finite(second.get("spot")) or SPOT
    gross_like = net = 0.0
    for osi, nxt in end_map.items():
        prev = start_map.get(osi)
        if prev is None:
            continue
        v0, v1 = _finite(prev.get("volume")), _finite(nxt.get("volume"))
        if v0 is None or v1 is None or v1 < v0:
            continue
        dv = v1 - v0
        gamma = _finite(nxt.get("gamma"))
        delta = _finite(nxt.get("delta"))
        mult = _finite(nxt.get("multiplier"))
        # An absent multiplier must be skipped like a missing gamma or delta,
        # not defaulted. The old `or 100.0` both invented a full-magnitude term
        # for a contract that never carried one AND conflated a measured 0.0
        # with an absent value, since 0.0 is falsy. gex_core._resolve_mult is
        # the reference shape: default only when the key is absent, then
        # require a finite positive value.
        if mult is None or mult <= 0:
            continue
        if gamma is None or gamma < 0 or delta is None:
            continue
        unit = gamma * mult * spot * spot * 0.01
        signed = 1.0 if str(nxt.get("type")).lower().startswith("c") else -1.0
        contrib = unit * abs(delta) * dv
        gross_like += contrib
        net += signed * contrib
    return {
        "window_gross_like": gross_like,
        "window_net": net,
        "interval": {"start": first.get("asof"), "end": second.get("asof")},
    }


def expected_packet() -> dict[str, Any]:
    return dict(EXPECTED_PACKET_T0)


def expected_window() -> dict[str, Any]:
    return dict(EXPECTED_WINDOW_T0_T1)


def source_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    return SOURCE_OBSERVATION_T0, SOURCE_OBSERVATION_T1
