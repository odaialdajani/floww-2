"""Pure WallDeskSnapshot.v1 projection from canonical exposure metrics.

Route/server/persistence-free. Consumes a source-shaped observation (the
same shape a live canonical producer emits) and returns a redacted packet
using only:

- domain.exposure_metrics.compute_raw_oi
- domain.exposure_metrics.compute_delta_weighted_oi
- domain.exposure_metrics.compute_volume_gamma

S3 rules, enforced here:

- This module never imports test fixtures or expected outputs. Identity
  (wall_id), spot and metadata all derive from the real input.
- Missing spot means UNAVAILABLE (numeric fields None, status
  "unavailable", reason SPOT_UNKNOWN) — never a substituted 100.
- A packet can legitimately have no usable values: zero usable contracts
  yields measured zeros with full coverage counts, not fabricated walls.
- project_window is the legacy per-OSI window helper. It applies the same
  canonical strictness (bool rejection, explicit-invalid multiplier
  rejection, unknown-type rejection, ticker-scope match, monotonic
  cumulative volume). The governed window path with session/provider/
  formula scoping and correction policy is
  services.solstice_enrichment.window_contract_activity; new consumers
  should prefer it.
"""

from __future__ import annotations

from typing import Any

from domain.exposure_metrics import (
    FORMULA_VERSION,
    abs_delta,
    compute_delta_weighted_oi,
    compute_raw_oi,
    compute_volume_gamma,
    is_valid_measurement,
    option_type_sign,
    resolve_multiplier,
)

SNAPSHOT_VERSION = "WallDeskSnapshot.v1"

# Metric IDs this packet actually projects (subset of METRIC_REGISTRY).
PACKET_METRIC_IDS = ("gex_gross_v1", "gex_net_v1", "dadgex_gross_v1", "dadgex_net_v1", "volume_gamma_v1")


def _unavailable_packet(
    observation: dict[str, Any], snapshot_id: str, reason: str, **extra: Any
) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "snapshot_version": SNAPSHOT_VERSION,
        "formula_version": FORMULA_VERSION,
        "metric_ids": list(PACKET_METRIC_IDS),
        "snapshot_id": snapshot_id,
        "ticker": observation.get("ticker"),
        "spot": None,
        "asof": observation.get("asof"),
        "source_received_at": observation.get("source_received_at"),
        "data_source": observation.get("data_source"),
        "wall_id": observation.get("wall_id"),
        "units": "USD/1% move",
        "status": "unavailable",
        "reason": reason,
        "raw_gross": None,
        "raw_net": None,
        "raw_usable": 0,
        "raw_missing_oi": 0,
        "raw_invalid": 0,
        "delta_gross": None,
        "delta_net": None,
        "delta_usable": 0,
        "delta_missing": 0,
        "delta_invalid": 0,
        "volume_gross_like": None,
        "volume_net": None,
        "volume_usable": 0,
        "volume_missing": 0,
        "volume_invalid": 0,
        "population": {"n_contracts": len(observation.get("contracts") or [])},
        "coverage": {"expiries": [], "stale": [], "missing_delta": []},
        "reason_codes": [reason],
    }
    packet.update(extra)
    return packet


def project_packet(observation: dict[str, Any], snapshot_id: str) -> dict[str, Any]:
    """Project one source-shaped observation into a redacted desk packet."""
    observation = observation if isinstance(observation, dict) else {}
    contracts = observation.get("contracts") or []
    spot = is_valid_measurement(observation.get("spot"))
    if spot is None:
        return _unavailable_packet(observation, snapshot_id, "SPOT_UNKNOWN")

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
    expiries = sorted({str(c.get("expiry")) for c in contracts if isinstance(c, dict) and c.get("expiry")})
    wall_reasons = list(reasons)
    if not observation.get("wall_id"):
        wall_reasons = sorted({*wall_reasons, "WALL_UNKNOWN"})

    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "formula_version": FORMULA_VERSION,
        "metric_ids": list(PACKET_METRIC_IDS),
        "snapshot_id": snapshot_id,
        "ticker": observation.get("ticker"),
        "spot": spot,
        "asof": observation.get("asof"),
        "source_received_at": observation.get("source_received_at"),
        "data_source": observation.get("data_source"),
        "wall_id": observation.get("wall_id"),
        "units": "USD/1% move",
        "status": "ok" if raw.usable or adj.usable or vol.usable else "empty",
        "reason": None if (raw.usable or adj.usable or vol.usable) else "NO_USABLE_CONTRACTS",
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
        "population": {"n_contracts": len(contracts)},
        "coverage": {
            "expiries": expiries,
            "stale": stale,
            "missing_delta": missing_delta,
        },
        "reason_codes": wall_reasons,
    }


def project_window(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """Window delta-volume activity between comparable cumulative observations.

    Per-OSI match on the intersection; each leg applies canonical strictness
    (bool/nonfinite rejection, explicit-invalid multiplier rejection via
    resolve_multiplier, unknown option-type rejection, |delta| weighting).
    Scope guards: ticker mismatch → unavailable (R10-07: SPY→QQQ must not
    yield 150); non-monotonic cumulative volume (retraction/reset) is
    skipped and counted, never differenced negative; missing spot on the
    end observation → unavailable. Returns None-valued sums with a reason
    when nothing is comparable — never an all-zero "measured" window.
    """
    first = first if isinstance(first, dict) else {}
    second = second if isinstance(second, dict) else {}
    interval = {"start": first.get("asof"), "end": second.get("asof")}
    t0, t1 = first.get("ticker"), second.get("ticker")
    if t0 is not None and t1 is not None and str(t0).upper() != str(t1).upper():
        return {
            "window_gross_like": None,
            "window_net": None,
            "status": "unavailable",
            "reason": "SCOPE_MISMATCH",
            "compared": 0,
            "skipped_nonmonotonic": 0,
            "interval": interval,
        }
    spot = is_valid_measurement(second.get("spot"))
    if spot is None:
        return {
            "window_gross_like": None,
            "window_net": None,
            "status": "unavailable",
            "reason": "SPOT_UNKNOWN",
            "compared": 0,
            "skipped_nonmonotonic": 0,
            "interval": interval,
        }
    start_map = {
        str(c.get("osi")): c for c in (first.get("contracts") or []) if isinstance(c, dict)
    }
    end_map = {
        str(c.get("osi")): c for c in (second.get("contracts") or []) if isinstance(c, dict)
    }
    gross_like = net = 0.0
    compared = 0
    skipped_nonmonotonic = 0
    for osi, nxt in end_map.items():
        prev = start_map.get(osi)
        if prev is None:
            continue
        v0 = is_valid_measurement(prev.get("volume"))
        v1 = is_valid_measurement(nxt.get("volume"))
        if v0 is None or v1 is None:
            continue
        if v1 < v0:
            skipped_nonmonotonic += 1
            continue
        dv = v1 - v0
        gamma = is_valid_measurement(nxt.get("gamma"))
        if gamma is None or gamma < 0:
            continue
        ad, _reason = abs_delta(nxt.get("delta"))
        if ad is None:
            continue
        mult, _mreason = resolve_multiplier(nxt if isinstance(nxt, dict) else {})
        if mult is None:
            continue
        sign = option_type_sign(nxt.get("type"))
        if sign is None:
            continue
        contrib = gamma * mult * spot * spot * 0.01 * ad * dv
        gross_like += contrib
        net += sign * contrib
        compared += 1
    if compared == 0:
        return {
            "window_gross_like": None,
            "window_net": None,
            "status": "unavailable",
            "reason": "NO_COMPARABLE_OBSERVATIONS",
            "compared": 0,
            "skipped_nonmonotonic": skipped_nonmonotonic,
            "interval": interval,
        }
    return {
        "window_gross_like": gross_like,
        "window_net": net,
        "status": "ok",
        "reason": None,
        "compared": compared,
        "skipped_nonmonotonic": skipped_nonmonotonic,
        "interval": interval,
    }
