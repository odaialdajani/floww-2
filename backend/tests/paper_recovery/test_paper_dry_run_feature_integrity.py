"""Focused regression — dry-run feature integrity (paper-recovery B12).

``backend/paper_trading.py::_build_feature_vector`` projected the model's
DECLARED feature names with ``float(row.get(name, 0.0) or 0.0)``: a feature
missing from the Mongo row — or stored as null — was silently substituted
with 0.0, and a non-numeric value crashed the whole dry run. Zero-fabricating
unknown data is exactly what the repo's data rule forbids ("missing, stale,
incomplete and unavailable data stay distinct; never substitute zero for an
unknown reading"). RED on the pre-fix tree; GREEN after: declared-missing or
null features are refused (ValueError) and the dry run SKIPS with an honest
reason instead of predicting on fabricated zeros. Observed zeros remain
legitimate values.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import paper_trading as pt  # noqa: E402


class TestVectorBuildsExactProjection:
    def test_complete_row_builds_exact_vector(self):
        X, names = pt._build_feature_vector({"a": 1.0, "b": 2}, ["a", "b"])
        assert names == ["a", "b"]
        assert X.tolist() == [[1.0, 2.0]]

    def test_zero_feature_value_is_kept(self):
        """An observed 0.0 is real data — it must not be refused or altered."""
        X, names = pt._build_feature_vector({"a": 0.0}, ["a"])
        assert names == ["a"]
        assert X.tolist() == [[0.0]]

    def test_derived_names_path_still_works(self):
        row = {"a": 1.0, "b": 2.0, "_id": "x", "ticker": "SPY", "date": "d",
               "feature_version": "v", "_computed_at": "t", "target_y": 1}
        X, names = pt._build_feature_vector(row, [])
        assert names == ["a", "b"]
        assert X.tolist() == [[1.0, 2.0]]


class TestUnknownFeaturesRefused:
    def test_declared_missing_feature_refused(self):
        with pytest.raises(ValueError, match="missing"):
            pt._build_feature_vector({"a": 1.0}, ["a", "b"])

    def test_null_feature_refused(self):
        with pytest.raises(ValueError, match="missing"):
            pt._build_feature_vector({"a": None}, ["a"])


class _Scaler:
    def transform(self, X):
        return X


def _patch_model(monkeypatch, feature_names, row, predict_calls):
    class _Model:
        def predict(self, X):
            predict_calls.append(1)
            return [1]

        def predict_proba(self, X):
            return [[0.2, 0.8]]

    monkeypatch.setattr(
        pt, "_load_active_model",
        lambda model_id=pt.ACTIVE_MODEL_ID: (_Model(), _Scaler(), feature_names))

    async def _row(ticker, names):
        return row

    monkeypatch.setattr(pt, "_latest_feature_row", _row)

    # Guard the user's real Mongo: persistence must never be reached on a
    # refused feature row (and pre-fix RED must not write to a live DB).
    class _Coll:
        async def insert_one(self, doc):
            raise AssertionError("dry-run persisted an intent despite unknown features")

    class _Db:
        def __getitem__(self, key):
            return _Coll()

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __getitem__(self, key):
            return _Db()

        def close(self):
            pass

    monkeypatch.setattr("motor.motor_asyncio.AsyncIOMotorClient", _Client)


class TestDryRunSkipsInsteadOfFabricating:
    @pytest.mark.asyncio
    async def test_dry_run_skips_when_declared_feature_missing(self, monkeypatch):
        predict_calls = []
        _patch_model(monkeypatch, ["a", "b"],
                     {"a": 1.0, "spot_price": 500.0, "date": "2026-10-27"},
                     predict_calls)
        result = await pt.daily_paper_trade_dry_run("SPY")
        assert result["action"] == "skip", result
        assert "missing" in result["reason"].lower()
        assert predict_calls == [], "model predicted on fabricated zero features"

    @pytest.mark.asyncio
    async def test_dry_run_skips_on_null_feature(self, monkeypatch):
        predict_calls = []
        _patch_model(monkeypatch, ["a", "b"],
                     {"a": 1.0, "b": None, "spot_price": 500.0, "date": "2026-10-27"},
                     predict_calls)
        result = await pt.daily_paper_trade_dry_run("SPY")
        assert result["action"] == "skip", result
        assert predict_calls == []

    @pytest.mark.asyncio
    async def test_dry_run_skips_on_nonnumeric_feature(self, monkeypatch):
        predict_calls = []
        _patch_model(monkeypatch, ["a", "b"],
                     {"a": 1.0, "b": "oops", "spot_price": 500.0, "date": "2026-10-27"},
                     predict_calls)
        result = await pt.daily_paper_trade_dry_run("SPY")
        assert result["action"] == "skip", result
        assert predict_calls == []

    @pytest.mark.asyncio
    async def test_dry_run_still_runs_on_complete_row(self, monkeypatch):
        """Complete declared features keep producing an intent (no Mongo write:
        the patched client's insert is reached only if prediction proceeds —
        assert the flow reaches prediction, then fails ONLY at the guarded
        insert, proving the feature path was taken)."""
        predict_calls = []
        _patch_model(monkeypatch, ["a", "b"],
                     {"a": 1.0, "b": 2.0, "spot_price": 500.0, "date": "2026-10-27"},
                     predict_calls)
        with pytest.raises(AssertionError, match="persisted an intent"):
            await pt.daily_paper_trade_dry_run("SPY")
        assert predict_calls, "model must be reached when all features are present"
