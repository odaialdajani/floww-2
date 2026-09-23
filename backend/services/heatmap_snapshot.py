"""
backend/services/heatmap_snapshot.py — Solstice immutable snapshot (T01/T29).

HeatmapSnapshotV2: one coherent point-in-time consumed by grid, inspector,
summary, alerts, AI packet and recorder. Compatibility adapter preserves the
existing endpoint shape during rollout.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def snapshot_id_for(payload: dict[str, Any]) -> str:
    """Content-addressed snapshot id from instrument+scope+inputs digest."""
    core = {
        "ticker": payload.get("ticker"),
        "expiries": payload.get("expiries_used"),
        "mode": payload.get("mode"),
        "spot": payload.get("spot"),
        "source": payload.get("data_source"),
        "basis": payload.get("exposure_basis"),
        "asof": payload.get("asof"),
    }
    digest = hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return f"snap_{digest}"


def build_snapshot_v2(payload: dict[str, Any], query_key: str = "") -> dict[str, Any]:
    """Wrap a build_heatmap payload with V2 identity + quality vocabulary."""
    snap_id = snapshot_id_for(payload)
    now = datetime.now(UTC).isoformat()
    quality = payload.get("quality") or {}
    return {
        "schemaVersion": "2",
        "snapshotId": snap_id,
        "queryKey": query_key or str(payload.get("ticker", "")),
        "instrument": {
            "displaySymbol": payload.get("ticker"),
            "currency": "USD",
        },
        "scope": {
            "expiries": payload.get("expiries_used", []),
            "metric": "gex_net_v1",
            "basis": payload.get("exposure_basis", "OI"),
            "signConvention": "call-minus-put",
            "formulaVersion": payload.get("formula_version", "gex.v2"),
        },
        "times": {
            "receivedAt": payload.get("source_received_at"),
            "calculatedAt": payload.get("asof", now),
            "sourceMinAt": payload.get("source_received_at"),
            "sourceMaxAt": payload.get("source_received_at"),
            "oiEffectiveDate": None,
        },
        "quality": {
            "state": "usable" if quality.get("setup_eligible", True) else "partial",
            "reasonCodes": quality.get("reasonCodes", []),
            "setupEligible": quality.get("setup_eligible", True),
            "executionEligible": False,
            "tradeSideCapability": quality.get("trade_side_capability", "none"),
        },
        "payload": payload,
    }


def to_legacy_payload(snapshot_v2: dict[str, Any]) -> dict[str, Any]:
    """Compatibility: existing grid/sidebar consume the inner payload unchanged."""
    p = dict(snapshot_v2.get("payload", {}))
    p["snapshotId"] = snapshot_v2.get("snapshotId")
    p["snapshotQueryKey"] = snapshot_v2.get("queryKey")
    return p
