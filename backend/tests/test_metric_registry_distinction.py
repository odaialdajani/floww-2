"""Registry distinction checks: VEX/DUO/DVO labels never silently interchange."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.exposure_metrics import FORMULA_VERSION, METRIC_REGISTRY  # noqa: E402
from domain.second_order_exposure import REGISTRY as SECOND_ORDER_REGISTRY  # noqa: E402


def test_canonical_registry_keeps_distinct_ids_units_and_bases():
    vex = METRIC_REGISTRY["vex_net_1volpt"]
    duo = METRIC_REGISTRY["duo_d2gex_dS2_v1"]
    dvo = METRIC_REGISTRY["dvo_dvega_dsigma_v1"]
    assert vex["basis"] == "VEX_1VOLPT"
    assert vex["units"] == "USD delta-notional/+1 vol pt"
    assert duo["basis"] == "DUO_D2GEX_DS2"
    assert duo["units"] == "USD/(1% move)^2"
    assert dvo["basis"] == "DVO_DVEGA_DSIGMA"
    assert dvo["units"] == "USD/unit-sigma"
    assert len({vex["basis"], duo["basis"], dvo["basis"]}) == 3
    assert all(row["version"] == FORMULA_VERSION for row in (vex, duo, dvo))


def test_second_order_module_matches_canonical_registry_rows():
    for key in ("duo_d2gex_dS2_v1", "dvo_dvega_dsigma_v1"):
        assert METRIC_REGISTRY[key] == {
            **SECOND_ORDER_REGISTRY[key],
            "version": FORMULA_VERSION,
        }


def test_existing_metric_ids_are_unchanged():
    assert METRIC_REGISTRY["gex_gross_v1"]["formula"] == "Σ u N"
    assert METRIC_REGISTRY["dadgex_net_v1"]["formula"] == "Σ c u N |δ|"
    assert METRIC_REGISTRY["volume_gamma_v1"]["formula"] == "Σ c u V"
    assert METRIC_REGISTRY["window_dadgex_v1"]["formula"] == "Σ c u |δ| ΔV(W)"
