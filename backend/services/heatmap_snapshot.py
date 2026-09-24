"""
backend/services/heatmap_snapshot.py — Solstice immutable snapshot (T01/T29, P02).

HeatmapSnapshotV2: one coherent point-in-time consumed by grid, inspector,
summary, alerts, AI packet and recorder. P02 (R4-01/R4-02):
- snapshotId binds the canonical CONTENT (normalized strikes/cells, scope,
  metric/formula versions, provenance) plus observation time. Changed exposure
  with an unchanged ID is impossible; the stored payload is a deep copy, so
  later mutation cannot rewrite an issued snapshot.
- normalize_quality(): one typed adapter, unknown-first. Missing quality is
  unavailable/ineligible — never eligible by default. Source, receipt and
  compute clocks are preserved separately and never equated.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "2"


def _canon_strikes(payload: dict[str, Any]) -> list:
    rows = []
    for r in payload.get("strikes") or []:
        if not isinstance(r, dict):
            continue
        rows.append({
            "strike": r.get("strike"), "gex": r.get("gex"),
            "call_gex": r.get("call_gex"), "put_gex": r.get("put_gex"),
        })
    return sorted(rows, key=lambda r: (r["strike"] is None, r["strike"]))


def _canon_grids(payload: dict[str, Any]) -> dict:
    out: dict[str, Any] = {}
    grid = payload.get("grid") or {}
    for key in ("grid", "charm_grid", "vex_grid", "vomma_grid"):
        section = grid.get(key) if isinstance(grid, dict) else None
        if not isinstance(section, dict):
            continue
        out[key] = {e: dict(sorted(col.items())) for e, col in sorted(section.items())
                    if isinstance(col, dict)}
    metrics = payload.get("metrics") or {}
    for name, g in ((metrics.get("grids") or {}).items() if isinstance(metrics, dict) else []):
        if isinstance(g, dict) and isinstance(g.get("grid"), dict):
            out[f"metrics.{name}"] = {
                e: dict(sorted(col.items())) for e, col in sorted(g["grid"].items())
                if isinstance(col, dict)}
    return out


def content_digest(payload: dict[str, Any]) -> str:
    """Digest of canonical inputs + scope + versions + provenance (no clocks)."""
    core = {
        "ticker": payload.get("ticker"),
        "expiries": sorted(payload.get("expiries_used") or []),
        "mode": payload.get("mode"),
        "dte": payload.get("dte"),
        "scalp": payload.get("scalp"),
        "spot": payload.get("spot"),
        "source": payload.get("data_source"),
        "chain_type": payload.get("chain_instrument_type"),
        "basis": payload.get("exposure_basis"),
        "formula": payload.get("formula_version", "gex.v2"),
        "strikes": _canon_strikes(payload),
        "grids": _canon_grids(payload),
    }
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]


def snapshot_id_for(payload: dict[str, Any]) -> str:
    """Observation identity: content digest + observation time + query scope.

    Two observations of identical content are distinct observations (asof
    differs); identical exposure can never share an ID with changed exposure
    because the content digest is part of the ID.
    """
    digest = hashlib.sha256(json.dumps({
        "content": content_digest(payload),
        "asof": payload.get("asof"),
        "ticker": payload.get("ticker"),
    }, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return f"snap_{digest}"


def normalize_quality(server_quality: dict[str, Any] | None) -> dict[str, Any]:
    """One typed quality adapter (R4-02). Unknown-first: a missing quality
    block is unavailable/ineligible, never eligible-by-default. Reason codes
    pass through; receipt/source/compute clocks stay separate fields."""
    if not isinstance(server_quality, dict):
        return {"state": "unavailable", "reasonCodes": ["QUALITY_UNKNOWN"],
                "setupEligible": False, "executionEligible": False,
                "tradeSideCapability": "none"}
    eligible = bool(server_quality.get("setup_eligible", False))
    reasons = list(server_quality.get("reasonCodes") or server_quality.get("reason_codes") or [])
    state = server_quality.get("state")
    if not isinstance(state, str) or not state:
        state = "partial" if eligible else "unavailable"
        if not eligible and "QUALITY_INELIGIBLE" not in reasons:
            reasons = [*reasons, "QUALITY_INELIGIBLE"]
    return {"state": state, "reasonCodes": reasons,
            "setupEligible": eligible, "executionEligible": False,
            "tradeSideCapability": server_quality.get("trade_side_capability", "none")}


def build_snapshot_v2(payload: dict[str, Any], query_key: str = "") -> dict[str, Any]:
    """Wrap a build_heatmap payload with V2 identity + quality vocabulary.

    The payload is deep-copied: later mutation of the caller's dict cannot
    rewrite this snapshot (R4-01).
    """
    frozen = copy.deepcopy(payload)
    snap_id = snapshot_id_for(frozen)
    now = datetime.now(UTC).isoformat()
    quality = normalize_quality(frozen.get("quality"))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "snapshotId": snap_id,
        "contentDigest": content_digest(frozen),
        "queryKey": query_key or str(frozen.get("ticker", "")),
        "instrument": {
            "displaySymbol": frozen.get("ticker"),
            "quoteInstrumentType": frozen.get("quote_instrument_type"),
            "chainInstrumentType": frozen.get("chain_instrument_type"),
            "currency": "USD",
        },
        "scope": {
            "expiries": frozen.get("expiries_used", []),
            "metric": "gex_net_v1",
            "basis": frozen.get("exposure_basis", "OI"),
            "signConvention": "call-minus-put",
            "formulaVersion": frozen.get("formula_version", "gex.v2"),
        },
        "times": {
            "receivedAt": frozen.get("source_received_at"),
            "calculatedAt": frozen.get("asof", now),
            "sourceMinAt": frozen.get("source_received_at"),
            "sourceMaxAt": frozen.get("source_received_at"),
            "oiEffectiveDate": frozen.get("oi_effective_date"),
        },
        "quality": quality,
        "payload": frozen,
    }


def to_legacy_payload(snapshot_v2: dict[str, Any]) -> dict[str, Any]:
    """Compatibility: existing grid/sidebar consume the inner payload unchanged."""
    p = copy.deepcopy(snapshot_v2.get("payload", {}))
    p["snapshotId"] = snapshot_v2.get("snapshotId")
    p["snapshotQueryKey"] = snapshot_v2.get("queryKey")
    return p
