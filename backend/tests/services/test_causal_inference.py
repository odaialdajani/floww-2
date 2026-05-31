"""
backend/tests/services/test_causal_inference.py

Tests for the Pearl causal inference engine.
Validates DAG operations, backdoor criterion, front-door criterion,
instrumental variables, do-calculus, and causal effect estimation.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from services.causal_inference import (
    BackdoorCriterion,
    CausalEffectEstimator,
    CausalGraph,
    DoCalculus,
    InstrumentalVariables,
)


# =============================================================================
# CausalGraph Tests
# =============================================================================
class TestCausalGraph:

    def test_add_edge(self):
        g = CausalGraph()
        g.add_edge("X", "Y")
        assert "Y" in g.get_children("X")
        assert "X" in g.get_parents("Y")

    def test_cycle_detection(self):
        g = CausalGraph()
        g.add_edge("X", "Y")
        g.add_edge("Y", "Z")
        with pytest.raises(ValueError, match="cycle"):
            g.add_edge("Z", "X")

    def test_ancestors(self):
        g = CausalGraph()
        g.add_edges([("A", "B"), ("B", "C"), ("D", "C")])
        assert g.get_ancestors("C") == {"A", "B", "D"}

    def test_descendants(self):
        g = CausalGraph()
        g.add_edges([("A", "B"), ("B", "C"), ("B", "D")])
        assert g.get_descendants("A") == {"B", "C", "D"}

    def test_d_separation_chain(self):
        """X → Z → Y: X and Y are d-separated given Z."""
        g = CausalGraph()
        g.add_edges([("X", "Z"), ("Z", "Y")])
        assert g.is_d_separated("X", "Y", {"Z"})
        assert not g.is_d_separated("X", "Y", set())

    def test_d_separation_fork(self):
        """X ← Z → Y: X and Y are d-separated given Z."""
        g = CausalGraph()
        g.add_edges([("Z", "X"), ("Z", "Y")])
        assert g.is_d_separated("X", "Y", {"Z"})
        assert not g.is_d_separated("X", "Y", set())

    def test_d_separation_collider(self):
        """X → Z ← Y: X and Y are d-separated given {}, but NOT given Z."""
        g = CausalGraph()
        g.add_edges([("X", "Z"), ("Y", "Z")])
        assert g.is_d_separated("X", "Y", set())
        assert not g.is_d_separated("X", "Y", {"Z"})

    def test_find_all_paths(self):
        g = CausalGraph()
        g.add_edges([("X", "Y"), ("X", "Z"), ("Z", "Y")])
        paths = g.find_all_paths("X", "Y")
        assert len(paths) == 2


# =============================================================================
# Backdoor Criterion Tests
# =============================================================================
class TestBackdoorCriterion:

    def test_simple_confounder(self):
        """Z → X → Y with U → X and U → Y: {U} is a valid adjustment set."""
        g = CausalGraph()
        g.add_edges([("Z", "X"), ("X", "Y"), ("U", "X"), ("U", "Y")])
        bd = BackdoorCriterion(g)
        assert bd.is_valid_adjustment_set("X", "Y", {"U"})
        assert not bd.is_valid_adjustment_set("X", "Y", {"Z"})

    def test_minimal_adjustment_set(self):
        g = CausalGraph()
        g.add_edges([("X", "Y"), ("U", "X"), ("U", "Y")])
        bd = BackdoorCriterion(g)
        minimal = bd.find_minimal_adjustment_set("X", "Y")
        assert minimal == {"U"}

    def test_no_adjustment_needed(self):
        """X → Y with no confounders: empty set is valid."""
        g = CausalGraph()
        g.add_edge("X", "Y")
        bd = BackdoorCriterion(g)
        assert bd.is_valid_adjustment_set("X", "Y", set())

    def test_descendant_not_valid(self):
        """Descendants of X cannot be in adjustment set."""
        g = CausalGraph()
        g.add_edges([("X", "M"), ("M", "Y"), ("U", "X"), ("U", "Y")])
        bd = BackdoorCriterion(g)
        assert not bd.is_valid_adjustment_set("X", "Y", {"M"})


# =============================================================================
# Instrumental Variables Tests
# =============================================================================
class TestInstrumentalVariables:

    def test_valid_instrument(self):
        """Z → X → Y with U → X and U → Y: Z is a valid instrument."""
        g = CausalGraph()
        g.add_edges([("Z", "X"), ("X", "Y"), ("U", "X"), ("U", "Y")])
        iv = InstrumentalVariables(g)
        assert iv.is_valid_instrument("Z", "X", "Y")

    def test_invalid_instrument_direct_effect(self):
        """Z → X → Y and Z → Y: Z is NOT a valid instrument (direct effect)."""
        g = CausalGraph()
        g.add_edges([("Z", "X"), ("X", "Y"), ("Z", "Y")])
        iv = InstrumentalVariables(g)
        assert not iv.is_valid_instrument("Z", "X", "Y")

    def test_2sls_recovers_true_effect(self):
        """2SLS should recover the true causal effect in a simple IV setup."""
        np.random.seed(42)
        n = 2000
        U = np.random.normal(0, 1, n)
        Z = np.random.normal(0, 1, n)
        X = 0.5 * Z + 0.3 * U + np.random.normal(0, 0.3, n)
        Y = 0.8 * X + 0.4 * U + np.random.normal(0, 0.3, n)

        df = pd.DataFrame({"X": X, "Y": Y, "Z": Z})

        g = CausalGraph()
        g.add_edges([("Z", "X"), ("X", "Y"), ("U", "X"), ("U", "Y")])
        iv = InstrumentalVariables(g)
        result = iv.estimate_2sls(df, "X", "Y", "Z")

        assert abs(result["causal_effect"] - 0.8) < 0.1
        assert result["p_value"] < 0.05
        assert not result["weak_instrument"]


# =============================================================================
# Do-Calculus Tests
# =============================================================================
class TestDoCalculus:

    def test_intervention_removes_edges(self):
        """do(X=x) should remove all incoming edges to X."""
        g = CausalGraph()
        g.add_edges([("Z", "X"), ("X", "Y")])
        dc = DoCalculus(g)
        g_do = dc.intervene({"X": 1.0})
        assert g_do.get_parents("X") == set()
        assert g_do.get_parents("Y") == {"X"}

    def test_interventional_mean(self):
        """E[Y | do(X=x)] should differ from E[Y | X=x] when confounders exist."""
        np.random.seed(42)
        n = 5000
        U = np.random.normal(0, 1, n)
        X = 0.5 * U + np.random.normal(0, 0.5, n)
        Y = 0.8 * X + 0.6 * U + np.random.normal(0, 0.3, n)

        df = pd.DataFrame({"X": X, "Y": Y, "U": U})

        g = CausalGraph()
        g.add_edges([("U", "X"), ("X", "Y"), ("U", "Y")])
        dc = DoCalculus(g)

        # Interventional mean should be close to 0 (no confounder effect)
        interventional = dc.compute_interventional_mean("Y", {"X": 0.0}, df)
        # The interventional mean of Y when do(X=0) should be close to 0
        # since Y = 0.8*0 + noise
        assert abs(interventional) < 0.5


# =============================================================================
# CausalEffectEstimator Tests
# =============================================================================
class TestCausalEffectEstimator:

    def test_auto_selects_backdoor(self):
        """Auto method should select backdoor when valid adjustment set exists."""
        np.random.seed(42)
        n = 1000
        U = np.random.normal(0, 1, n)
        X = 0.5 * U + np.random.normal(0, 0.5, n)
        Y = 0.8 * X + 0.6 * U + np.random.normal(0, 0.3, n)

        df = pd.DataFrame({"X": X, "Y": Y, "U": U})

        g = CausalGraph()
        g.add_edges([("U", "X"), ("X", "Y"), ("U", "Y")])
        est = CausalEffectEstimator(g)
        result = est.estimate_effect(df, "X", "Y", method="auto")

        assert result["method"] == "backdoor"
        assert abs(result["causal_effect"] - 0.8) < 0.15
        assert result["p_value"] < 0.05

    def test_iv_method(self):
        """IV method should recover causal effect with valid instrument."""
        np.random.seed(42)
        n = 2000
        U = np.random.normal(0, 1, n)
        Z = np.random.normal(0, 1, n)
        X = 0.5 * Z + 0.3 * U + np.random.normal(0, 0.3, n)
        Y = 0.8 * X + 0.4 * U + np.random.normal(0, 0.3, n)

        df = pd.DataFrame({"X": X, "Y": Y, "Z": Z})

        g = CausalGraph()
        g.add_edges([("Z", "X"), ("X", "Y"), ("U", "X"), ("U", "Y")])
        est = CausalEffectEstimator(g)
        result = est.estimate_effect(df, "X", "Y", method="iv")

        assert abs(result["causal_effect"] - 0.8) < 0.15
        assert result["p_value"] < 0.05

    def test_regression_fallback(self):
        """Regression method should work even without causal graph."""
        np.random.seed(42)
        n = 500
        X = np.random.normal(0, 1, n)
        Y = 0.5 * X + np.random.normal(0, 0.5, n)

        df = pd.DataFrame({"X": X, "Y": Y})

        est = CausalEffectEstimator()
        result = est.estimate_effect(df, "X", "Y", method="regression")

        assert abs(result["causal_effect"] - 0.5) < 0.1
        assert "warning" in result  # Should warn about no causal adjustment


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
