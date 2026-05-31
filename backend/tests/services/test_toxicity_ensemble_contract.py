"""
backend/tests/services/test_toxicity_ensemble_contract.py

Contract tests for the toxicity ensemble.
Verifies Platt scaler shape, monotonicity, and ensemble output contract.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest

# ── Bootstrap: mock heavy dependencies ──────────────────────────────────

# Stub services.observability — setdefault only; NEVER replace
# sys.modules["services"]: clobbering the package strips __path__ and poisons
# `from services.X import ...` collection for the rest of the session.
obs = types.ModuleType("services.observability")
obs.duckdb_queue_depth = type("M", (), {"set": lambda s, v: None})()
obs.duckdb_batch_size = type("M", (), {"observe": lambda s, v: None})()
sys.modules.setdefault("services.observability", obs)

# Mock torch (not available in test env)
torch_mock = types.ModuleType("torch")
torch_mock.nn = types.ModuleType("torch.nn")
torch_mock.nn.Module = type("Module", (), {"__init__": lambda s: None})
torch_mock.tensor = lambda *a, **kw: None
torch_mock.float32 = None
torch_mock.device = lambda *a, **kw: "cpu"
torch_mock.no_grad = lambda: types.ModuleType("_ctx")
torch_mock.no_grad.__enter__ = lambda s: None
torch_mock.no_grad.__exit__ = lambda s, *a: None
# setdefault only — use real torch/scipy when installed (they are, locally),
# fall back to the stub only when absent (e.g. CI without torch). NEVER replace
# real modules: clobbering sys.modules["scipy"] breaks scipy-using tests later in
# the session (test_train_spy_v2, test_pipeline_integration).
if importlib.util.find_spec("torch") is None:  # stub only when truly absent (minimal CI)
    sys.modules.setdefault("torch", torch_mock)
    sys.modules.setdefault("torch.nn", torch_mock.nn)

# Stub scipy (fallback only)
scipy_mock = types.ModuleType("scipy")
scipy_mock.optimize = types.ModuleType("scipy.optimize")
scipy_mock.optimize.minimize = lambda *a, **kw: type("R", (), {"x": [1.0, 0.0]})()
if importlib.util.find_spec("scipy") is None:  # stub only when truly absent
    sys.modules.setdefault("scipy", scipy_mock)
    sys.modules.setdefault("scipy.optimize", scipy_mock.optimize)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.ml_ensemble import PlattScaler, ToxicityEnsemble

# ── PlattScaler tests ───────────────────────────────────────────────────


class TestPlattScalerContract:
    """Contract: PlattScaler outputs are valid probabilities."""

    def test_output_in_unit_interval_after_fit(self):
        """Calibrated probabilities must be in [0, 1] after fitting."""
        ps = PlattScaler()
        rng = np.random.RandomState(42)
        scores = np.concatenate([rng.normal(0.02, 0.01, 200), rng.normal(0.15, 0.05, 50)])
        labels = np.concatenate([np.zeros(200), np.ones(50)])
        ps.fit(scores, labels)
        out = ps.predict_proba(scores)
        assert np.all((out >= 0.0) & (out <= 1.0)), f"Platt output out of range: min={out.min()}, max={out.max()}"

    def test_output_in_unit_interval_without_fit(self):
        """Unfitted PlattScaler fallback must also produce [0, 1]."""
        ps = PlattScaler()
        scores = np.array([0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0])
        out = ps.predict_proba(scores)
        assert np.all((out >= 0.0) & (out <= 1.0)), f"Unfitted Platt out of range: {out}"

    def test_monotonic_after_fit(self):
        """Higher scores should yield higher calibrated probabilities."""
        ps = PlattScaler()
        scores = np.linspace(-3, 3, 21)
        labels = (scores > 0).astype(int)
        ps.fit(scores, labels)
        out = ps.predict_proba(scores)
        diffs = np.diff(out)
        assert np.all(diffs >= -1e-6), f"Platt not monotonic; negative diffs at: {np.where(diffs < 0)[0]}"

    def test_constant_scores_no_nan(self):
        """All-identical scores must not produce NaN."""
        ps = PlattScaler()
        scores = np.array([0.5, 0.5, 0.5, 0.5])
        out = ps.predict_proba(scores)
        assert not np.any(np.isnan(out)), f"NaN in output for constant scores: {out}"

    def test_single_element_no_crash(self):
        """Single-element input must not crash."""
        ps = PlattScaler()
        out = ps.predict_proba(np.array([0.5]))
        assert len(out) == 1
        assert 0.0 <= out[0] <= 1.0

    def test_extreme_scores_saturate(self):
        """Very large positive/negative scores should saturate, not overflow."""
        ps = PlattScaler()
        scores = np.array([-1000.0, -100.0, 0.0, 100.0, 1000.0])
        out = ps.predict_proba(scores)
        assert np.all(np.isfinite(out)), f"Non-finite values: {out}"
        assert np.all((out >= 0.0) & (out <= 1.0)), f"Out of range: {out}"


# ── ToxicityEnsemble tests ──────────────────────────────────────────────


class TestToxicityEnsembleContract:
    """Contract: ToxicityEnsemble returns well-formed output."""

    def test_update_returns_unit_float_per_horizon(self):
        """Each horizon probability must be a float in [0, 1]."""
        ens = ToxicityEnsemble(seq_len=10, latent_dim=4)
        result = ens.update(vpin=0.5, qi=0.3)
        probs = result["ensemble_probabilities"]
        assert len(probs) == 4, f"Expected 4 horizons, got {len(probs)}"
        for key, val in probs.items():
            assert isinstance(val, (float, int, np.floating)), f"{key}: type={type(val)}"
            assert 0.0 <= float(val) <= 1.0, f"{key}: {val} out of range"

    def test_update_returns_component_scores(self):
        """Component scores dict must have all three detectors."""
        ens = ToxicityEnsemble(seq_len=10, latent_dim=4)
        result = ens.update(vpin=0.5, qi=0.3)
        components = result["component_scores"]
        assert "cnn_ae" in components
        assert "statistical" in components
        assert "forecast_residual" in components

    def test_update_returns_anomaly_flags(self):
        """Anomaly flags must be present and boolean."""
        ens = ToxicityEnsemble(seq_len=10, latent_dim=4)
        result = ens.update(vpin=0.5, qi=0.3)
        assert "cnn_anomaly" in result
        assert "statistical_anomaly" in result
        assert isinstance(result["cnn_anomaly"], (bool, np.bool_))
        assert isinstance(result["statistical_anomaly"], (bool, np.bool_))

    def test_update_status_active(self):
        """Status should be 'active' after update."""
        ens = ToxicityEnsemble(seq_len=10, latent_dim=4)
        result = ens.update(vpin=0.5, qi=0.3)
        assert result["status"] == "active"

    def test_multiple_updates_deterministic(self):
        """Same inputs should produce same outputs."""
        ens = ToxicityEnsemble(seq_len=10, latent_dim=4)
        r1 = ens.update(vpin=0.5, qi=0.3)
        r2 = ens.update(vpin=0.5, qi=0.3)
        for key in r1["ensemble_probabilities"]:
            assert r1["ensemble_probabilities"][key] == r2["ensemble_probabilities"][key],                 f"{key} differs: {r1['ensemble_probabilities'][key]} vs {r2['ensemble_probabilities'][key]}"

    def test_extreme_vpin_values(self):
        """Extreme VPIN values should not crash."""
        ens = ToxicityEnsemble(seq_len=10, latent_dim=4)
        for vpin in [0.0, 0.99, 1.0, -0.5]:
            result = ens.update(vpin=vpin, qi=0.0)
            probs = result["ensemble_probabilities"]
            for key, val in probs.items():
                assert 0.0 <= float(val) <= 1.0, f"vpin={vpin}: {key}={val} out of range"
