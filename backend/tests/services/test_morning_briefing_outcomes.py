"""
backend/tests/services/test_morning_briefing_outcomes.py

The morning brief's alert_outcomes section: reads the nightly cron's
precomputed Mongo snapshot, fails soft, and shapes rules for the brief.
Tests pin the snapshot→brief contract WITHOUT Mongo (monkeypatched async
readers), so they run in the standard offline suite.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services import morning_briefing as mb  # noqa: E402


def _snapshot_doc() -> dict:
    """Shape written by cron_outcomes.py (flow_outcome_cache, status=ok)."""
    return {
        "status": "ok",
        "computed_at": "2099-01-01T00:00:00+00:00",
        "horizon_sessions": 2,
        "sigma_k": 0.75,
        "overall": {"n_measured": 40, "precision": 0.35},
        "per_rule": {
            "SCORE": {"n_alerts": 30, "n_measured": 28, "n_censored": 2,
                      "n_controls": 100, "hits": 12, "precision": 0.4286,
                      "precision_ci": [0.25, 0.62], "control_rate": 0.1,
                      "lift": 0.3286, "lift_ci": [0.1, 0.55],
                      "median_mfe_sigma": 1.2, "median_mae_sigma": -0.6,
                      "uncalibrated": False},
            "0DTE": {"n_alerts": 3, "n_measured": 3, "n_censored": 0,
                     "n_controls": 0, "hits": 1, "precision": None,
                     "precision_ci": None, "control_rate": None, "lift": None,
                     "lift_ci": None, "median_mfe_sigma": None,
                     "median_mae_sigma": None, "uncalibrated": True},
        },
    }


def _calibration_doc() -> dict:
    """Shape written by cron_outcomes.py (flow_outcome_cache, calibration_latest)."""
    return {
        "status": "ok",
        "stage": 1,
        "n": 84,
        "method_note": "decile",
        "model": {"kind": "decile", "isotonic": False},
    }


def _run_with_snapshot(monkeypatch, doc, calibration=None):
    async def fake_read(horizon=2):
        return doc

    async def fake_read_cal(horizon=2):
        return calibration

    monkeypatch.setattr(mb, "_read_mongo_snapshot", fake_read, raising=False)
    monkeypatch.setattr(mb, "_read_calibration_snapshot", fake_read_cal, raising=False)
    mb._outcome_cache.clear()
    return asyncio.run(mb._outcome_ledger_metrics())


def test_brief_outcomes_shapes_rules_and_overall(monkeypatch):
    out = _run_with_snapshot(monkeypatch, _snapshot_doc(), _calibration_doc())
    assert out["available"] is True
    assert out["computed_at"] == "2099-01-01T00:00:00+00:00"
    assert out["overall_precision"] == 0.35
    by_rule = {r["rule"]: r for r in out["rules"]}
    assert by_rule["SCORE"]["n_measured"] == 28
    assert by_rule["SCORE"]["precision"] == 0.4286
    assert by_rule["SCORE"]["lift"] == 0.3286
    assert by_rule["SCORE"]["control_rate"] == 0.1
    assert by_rule["SCORE"]["uncalibrated"] is False
    assert by_rule["0DTE"]["uncalibrated"] is True
    assert by_rule["0DTE"]["precision"] is None  # never a fabricated rate
    # calibration enrichment rides along from the nightly snapshot
    assert out["calibration"]["stage"] == 1
    assert out["calibration"]["n"] == 84
    assert out["calibration"]["method_note"] == "decile"


def test_brief_outcomes_fail_soft_without_snapshot(monkeypatch):
    out = _run_with_snapshot(monkeypatch, None)
    assert out["available"] is False
    assert "reason" in out
    assert "no snapshot" in out["reason"]


def test_brief_outcomes_fail_soft_on_reader_error(monkeypatch):
    async def boom(horizon=2):
        raise RuntimeError("mongo down")

    monkeypatch.setattr(mb, "_read_mongo_snapshot", boom, raising=False)
    mb._outcome_cache.clear()
    out = asyncio.run(mb._outcome_ledger_metrics())
    assert out["available"] is False
    assert "failed" in out.get("reason", "")


def test_brief_outcomes_calibration_failure_is_not_fatal(monkeypatch):
    """A broken calibration reader must not take down the outcomes section."""

    async def bad_cal(horizon=2):
        raise RuntimeError("calibration cache corrupt")

    monkeypatch.setattr(mb, "_read_calibration_snapshot", bad_cal, raising=False)
    out = _run_with_snapshot(monkeypatch, _snapshot_doc())
    assert out["available"] is True
    assert "calibration" not in out


def test_brief_includes_alert_outcomes_key_in_metrics():
    """build_briefing's metrics dict carries the alert_outcomes section —
    verified structurally so no Mongo/network is needed."""
    import inspect

    src = inspect.getsource(mb.build_briefing)
    assert "await _outcome_ledger_metrics()" in src
    assert '"alert_outcomes"' in src


def _ao(*rules, overall=None, available=True):
    return {
        "available": available,
        "rules": [
            {"rule": r[0], "n_measured": r[1], "precision": r[2],
             "lift": r[3], "uncalibrated": r[4]}
            for r in rules
        ],
        "overall_precision": overall,
    }


def test_narrative_line_unavailable_is_silent():
    """No measured state → no sentence. The brief never fabricates."""
    assert mb._outcome_narrative_line(None) == ""
    assert mb._outcome_narrative_line({"available": False, "reason": "x"}) == ""
    assert mb._outcome_narrative_line(_ao()) == ""


def test_narrative_line_cold_ledger_counts_not_rates():
    out = mb._outcome_narrative_line(
        _ao(("SCORE", 40, None, None, True), ("WHALE", 3, None, None, True)))
    assert out == "Alert ledger: 43 measured alert(s) — not yet enough for per-rule hit rates."


def test_narrative_line_quotes_best_and_negative_lift():
    out = mb._outcome_narrative_line(_ao(
        ("SCORE", 28, 0.4286, 0.3286, False),
        ("WHALE", 10, 0.2, -0.15, False),
        ("0DTE", 8, None, None, True),   # uncalibrated — never quoted
        overall=0.35,
    ))
    assert out.startswith("Measured alert quality: ")
    assert "SCORE 43% hit, lift +0.33" in out
    assert "WHALE lift -0.15" in out
    assert "0DTE" not in out          # uncalibrated rule stays out of prose
    assert out.endswith("— overall 35%.")
