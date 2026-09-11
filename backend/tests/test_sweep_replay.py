"""
backend/tests/test_sweep_replay.py — Agent D (D2 replay determinism).

Sweep recorder + replayer: same recorded snapshot ⇒ byte-identical alerts.
Freeze list (MASTER_PLAN §13): rows, baselines, prev-OI, regimes,
gex_context, oi_tags, calibration blob, frozen mins_since_open / asof.
The engine mints both clocks live (flow_alerts.eval_institutional:605 and
_mk_alert:497), so replay freezes them via mock — no prod-logic change.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta


def _ensure_imports():
    if "services.sweep_replay" not in sys.modules:
        sys.path.insert(0, "/Users/nav/Documents/GitHub/floww/backend")


_ensure_imports()

FROZEN_ASOF = "2026-09-05T10:00:00-04:00"
FROZEN_MINS = 30.0


def _future_exp(biz_days: int) -> str:
    d = date.today()
    added = 0
    while added < biz_days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d.isoformat()


def _raw(under="SPY", occ="O:SPY260924C00760000", typ="call", strike=760.0,
         exp=None, vol=200000, oi=2000, iv=0.5, delta=0.3, spot=758.0):
    return [under, occ, typ, strike, exp or _future_exp(1), vol, oi, iv, delta, spot]


def _snapshot():
    from services.flow_alerts import norm_rows
    from services.sweep_replay import record_sweep

    rows = norm_rows([_raw()])
    assert len(rows) == 1
    under = rows[0]["under"]
    ckey = rows[0]["ckey"]
    return record_sweep(
        rows=rows,
        baselines={under: {"avg": 50000.0, "std": 20000.0, "days": 10}},
        prev_oi={ckey: 1500.0},
        regimes={under: "negative"},
        gex_context={under: {"gamma_imbalance": {
            "gamma_imbalance_pct": -1.2, "regime": "negative"}}},
        oi_tags={},
        calibration=None,
        opts={},
        asof=FROZEN_ASOF,
        mins_since_open=FROZEN_MINS,
    )


def test_record_captures_freeze_list():
    snap = _snapshot()
    for key in ("rows", "baselines", "prev_oi", "regimes", "gex_context",
                "oi_tags", "calibration", "opts", "asof", "mins_since_open"):
        assert key in snap, f"snapshot missing freeze-list key: {key}"
    assert snap["asof"] == FROZEN_ASOF
    assert snap["mins_since_open"] == FROZEN_MINS


def test_replay_fires_and_freezes_clock():
    from services.sweep_replay import replay

    alerts = replay(_snapshot())
    assert len(alerts) >= 1, "fixture must fire at least one alert"
    for a in alerts:
        assert a["asof"] == FROZEN_ASOF
        assert a["mins_since_open"] == FROZEN_MINS


def test_replay_is_byte_deterministic():
    from services.sweep_replay import replay

    snap = _snapshot()
    first = json.dumps(replay(snap), sort_keys=True, default=str)
    second = json.dumps(replay(snap), sort_keys=True, default=str)
    assert first == second


def test_snapshot_survives_json_roundtrip():
    from services.sweep_replay import replay

    snap = json.loads(json.dumps(_snapshot(), default=str))
    alerts = replay(snap)
    assert len(alerts) >= 1
    assert all(a["asof"] == FROZEN_ASOF for a in alerts)


def test_digest_stable_and_sensitive_to_input_change():
    import copy

    from services.sweep_replay import alert_digest, replay

    snap = _snapshot()
    assert alert_digest(replay(snap)) == alert_digest(replay(snap))
    mutated = copy.deepcopy(snap)
    mutated["rows"][0]["vol"] = (mutated["rows"][0]["vol"] or 0) + 50000
    assert alert_digest(replay(mutated)) != alert_digest(replay(snap))


def test_golden_fixture_replays_deterministic():
    import pathlib

    from services.sweep_replay import alert_digest, replay

    snap = json.loads(pathlib.Path("tests/fixtures/sweep_golden_v1.json").read_text())
    assert snap.get("schema") == "sweep_replay/v1"
    first, second = replay(snap), replay(snap)
    assert len(first) >= 1
    assert alert_digest(first) == alert_digest(second)
    assert all(a["asof"] == snap["asof"] for a in first)
    assert all(a["mins_since_open"] == snap["mins_since_open"] for a in first)


def test_record_captures_moves_legs():
    from services.sweep_replay import record_sweep

    legs = [{"stamp_date": "2026-09-06", "last_price": 761.0, "move_pct": 0.4}]
    snap = record_sweep(rows=[], moves_legs=legs)
    assert snap["moves_legs"] == legs
    snap["moves_legs"].append({"stamp_date": "2026-09-07"})
    assert legs == [{"stamp_date": "2026-09-06", "last_price": 761.0, "move_pct": 0.4}]


def test_diff_alerts_reports_added_removed_changed():
    from services.sweep_replay import diff_alerts, replay

    snap = _snapshot()
    base = replay(snap)
    assert diff_alerts(base, base)["identical"] is True
    changed = [dict(a, why=(a.get("why") or "") + " [drift]") for a in base]
    d = diff_alerts(base, changed)
    assert d["identical"] is False
    assert len(d["changed"]) == len(base)
    assert d["added"] == [] and d["removed"] == []
    dropped = base[1:]
    d2 = diff_alerts(base, dropped)
    assert len(d2["removed"]) == 1 and d2["added"] == []
