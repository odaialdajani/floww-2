"""
backend/services/sweep_replay.py — Agent D (D2 replay determinism).

Sweep recorder + replayer for the institutional alert engine. The engine
mints two clocks live (`eval_institutional` builds `asof` from
`datetime.now`, `_mk_alert` stamps `mins_since_open` per alert), so a
recorded snapshot freezes both and replay re-injects them via mock —
no production-logic change, byte-identical alerts from the same input.

Freeze list: rows, baselines, prev-OI, regimes, gex_context, oi_tags,
calibration blob, opts, asof, mins_since_open.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from typing import Any
from unittest import mock

SCHEMA = "sweep_replay/v1"


def record_sweep(
    rows: list[dict],
    baselines: dict | None = None,
    prev_oi: dict | None = None,
    regimes: dict | None = None,
    gex_context: dict | None = None,
    oi_tags: dict | None = None,
    calibration: Any = None,
    opts: dict | None = None,
    asof: str = "",
    mins_since_open: float | None = None,
    moves_legs: list[dict] | None = None,
) -> dict:
    """Freeze one sweep's engine inputs (deep-copied) into a snapshot."""
    return {
        "schema": SCHEMA,
        "rows": copy.deepcopy(rows),
        "baselines": copy.deepcopy(baselines or {}),
        "prev_oi": copy.deepcopy(prev_oi or {}),
        "regimes": copy.deepcopy(regimes or {}),
        "gex_context": copy.deepcopy(gex_context or {}),
        "oi_tags": copy.deepcopy(oi_tags or {}),
        "calibration": copy.deepcopy(calibration),
        "opts": copy.deepcopy(opts or {}),
        "asof": asof,
        "mins_since_open": mins_since_open,
        "moves_legs": copy.deepcopy(moves_legs or []),
    }


def _frozen_datetime_cls(frozen: datetime):
    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ARG003 — signature must match datetime.now
            return frozen

    return _FrozenDateTime


def replay(snapshot: dict) -> list[dict]:
    """Re-run the engine on a recorded snapshot; byte-identical per input."""
    from services.flow_alerts import eval_institutional

    frozen = datetime.fromisoformat(snapshot["asof"])
    opts = {**(snapshot.get("opts") or {}), "calibration": snapshot.get("calibration")}
    with (
        mock.patch(
            "services.flow_alerts.datetime", _frozen_datetime_cls(frozen)
        ),
        mock.patch(
            "services.flow_alerts.minutes_since_open_now",
            return_value=snapshot.get("mins_since_open"),
        ),
    ):
        return eval_institutional(
            copy.deepcopy(snapshot.get("rows") or []),
            baselines=copy.deepcopy(snapshot.get("baselines") or {}),
            prev_oi=copy.deepcopy(snapshot.get("prev_oi") or {}),
            regimes=copy.deepcopy(snapshot.get("regimes") or {}),
            opts=opts,
            gex_context=copy.deepcopy(snapshot.get("gex_context") or {}),
            oi_tags=copy.deepcopy(snapshot.get("oi_tags") or {}),
        )


def alert_digest(alerts: list[dict]) -> str:
    """Stable sha256 over canonical JSON — drift detector fails loudly."""
    canon = json.dumps(alerts, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode()).hexdigest()


def _canon(alert: dict) -> str:
    return json.dumps(alert, sort_keys=True, default=str)


def diff_alerts(before: list[dict], after: list[dict]) -> dict:
    """Keyed diff of two alert lists: added/removed/changed + identical flag.

    The drift detector's loud failure: digest mismatch says *that* the
    engine drifted; this says *what* (which keys, which side).
    """
    b = {str(a.get("key")): a for a in before}
    c = {str(a.get("key")): a for a in after}
    added = sorted(k for k in c if k not in b)
    removed = sorted(k for k in b if k not in c)
    changed = sorted(k for k in b if k in c and _canon(b[k]) != _canon(c[k]))
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "identical": not (added or removed or changed),
    }
