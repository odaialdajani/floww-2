"""C3 — does real Public-shaped input reach visible Triad values?

This is the question the C3 audit asked and that the previous work did not
answer. `/api/public/chain/{ticker}` returns contracts carrying `gamma`,
`delta`, `oi`, `volume`, `strike`, `expiry`, `type` — and no computed `gex`.
The Triad read `c.gex`. So with real adapter input every cell was unknown, the
projection produced zero renderable rows, and the view fell through to its
fallback. The frontend tests passed because they INSERTED a `gex` field the
real adapter never emits.

The fixture below is built to the adapter's real output shape — read off
`services/public_api_adapter.py::_fetch_chain_live`, the `contracts.append({...})`
block — including `exposure_basis` and NO `gex` key. If this test ever starts
passing trivially, someone has added a synthetic `gex` to the fixture; it is
asserted absent.

The load-bearing claim is PARITY: the projection's net exposure must equal
`domain.exposure_metrics.compute_raw_oi(...).net`, the canonical registry
formula. That is what makes this a projection onto the existing engine rather
than a fourth Greek engine.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from domain.exposure_metrics import compute_raw_oi  # noqa: E402
from services.triad_projection import (  # noqa: E402
    annotate_contract_exposure,
    exposure_parity,
    project_triad_from_chain,
)

SPOT = 450.0
EXP_A = "2026-09-30"
EXP_B = "2026-10-16"


def adapter_contract(**over):
    """A row shaped exactly as the live adapter emits it.

    Field names and the absent `gex` are the point of this fixture.
    """
    row = {
        "osi": "SPY   260930C00450000",
        "expiry": EXP_A,
        "series": "SPY",
        "T": 30 / 365,
        "T_floored": 30 / 365,
        "T_model": "actual/365-exact",
        "type": "call",
        "strike": 450,
        "strike_exact": "450.0",
        "oi": 1000,
        "oi_effective_date": "2026-09-27",
        "iv": 0.21,
        "delta": 0.52,
        "gamma": 0.011,
        "theta": -0.12,
        "vega": 0.09,
        "greeks_source": "public_api",
        "bid": 12.0,
        "ask": 12.4,
        "mid": 12.2,
        "last": 12.3,
        "received_at": "2026-09-28T14:31:02Z",
        "volume": 500,
        "oi_source": "public_api",
        "exposure_basis": "OI",
        "chain_instrument_type": "EQUITY",
    }
    row.update(over)
    return row


def adapter_payload(contracts, **over):
    return {
        "ticker": "SPY",
        "spot": SPOT,
        "expiries": sorted({c["expiry"] for c in contracts if c.get("expiry")}),
        "contracts": contracts,
        "data_source": "public_api",
        "stale": False,
        **over,
    }


class TestTheFixtureIsActuallyAdapterShaped:
    def test_the_fixture_carries_no_computed_gex(self):
        """If a `gex` key appeared here, the whole premise of this file is void."""
        for row in (adapter_contract(), adapter_contract(type="put", oi=800, strike=460)):
            assert "gex" not in row

    def test_the_fixture_carries_the_fields_the_adapter_really_emits(self):
        row = adapter_contract()
        for field in ("gamma", "delta", "oi", "volume", "strike", "expiry", "type", "exposure_basis"):
            assert field in row, f"{field} is part of the real adapter row shape"


class TestRealInputNowReachesValues:
    def test_annotation_produces_a_real_number_from_adapter_fields(self):
        out = annotate_contract_exposure([adapter_contract()], SPOT)
        assert len(out) == 1
        assert out[0]["gex"] is not None
        assert out[0]["gex"] > 0, "a call contributes positively"
        assert out[0]["gex_basis"] == "OI"
        assert out[0]["gex_reason"] is None

    def test_projection_of_real_input_has_renderable_rows(self):
        """The actual C3 question. This was zero before."""
        payload = adapter_payload(
            [
                adapter_contract(),
                adapter_contract(type="put", oi=800, strike=460, delta=-0.35),
                adapter_contract(strike=455, oi=600, expiry=EXP_B),
            ]
        )
        packet = project_triad_from_chain(payload)
        assert packet["strikes"], "real adapter input must yield renderable rows"
        assert len(packet["strikes"]) == 3
        assert packet["coverage"]["usable"] == 3
        assert all(r["gex"] is not None for r in packet["strikes"])
        assert packet["nodes"]["net_gex"] is not None
        assert packet["nodes"]["king"] is not None

    def test_projection_is_json_safe_and_carries_provenance(self):
        import json

        packet = project_triad_from_chain(adapter_payload([adapter_contract()]))
        blob = json.dumps(packet)
        assert "NaN" not in blob and "Infinity" not in blob
        round_tripped = json.loads(blob)
        assert round_tripped["projection_version"]
        assert round_tripped["formula_version"]
        assert "gex_gross_v1" in round_tripped["metric_ids"]


class TestItIsAProjectionNotAFourthEngine:
    def test_net_matches_the_canonical_registry_formula(self):
        """`gex_net_v1` is `Σ c u N`. The projection must equal it exactly."""
        contracts = [
            adapter_contract(),
            adapter_contract(type="put", oi=800, strike=460),
            adapter_contract(strike=455, oi=600, expiry=EXP_B),
            adapter_contract(type="put", oi=1500, strike=445, gamma=0.02),
        ]
        result = exposure_parity(contracts, SPOT)
        assert result["agrees"], (
            f"projection net {result['projected_net']} != canonical {result['canonical_net']}"
        )
        assert result["projected_net"] == pytest.approx(result["canonical_net"], rel=1e-12)

    def test_per_strike_net_equals_the_canonical_net_over_the_same_rows(self):
        contracts = [adapter_contract(), adapter_contract(type="put", oi=800, strike=460)]
        packet = project_triad_from_chain(adapter_payload(contracts))
        canonical = compute_raw_oi(contracts, SPOT)
        assert packet["nodes"]["net_gex"] == pytest.approx(canonical.net, rel=1e-12)

    def test_the_canonical_gross_and_net_remain_distinct(self):
        """Gross is unsigned. Collapsing them is the classic error."""
        contracts = [adapter_contract(), adapter_contract(type="put", oi=800, strike=460)]
        canonical = compute_raw_oi(contracts, SPOT)
        assert canonical.gross > 0
        assert canonical.net < canonical.gross, "signing must reduce the magnitude"
        packet = project_triad_from_chain(adapter_payload(contracts))
        assert abs(packet["nodes"]["net_gex"]) < canonical.gross


class TestOpposingContractsNetRatherThanOverwrite:
    def test_a_call_and_a_put_at_one_strike_sum(self):
        payload = adapter_payload(
            [
                adapter_contract(type="call", oi=1000),
                adapter_contract(type="put", oi=800),
            ]
        )
        packet = project_triad_from_chain(payload)
        assert len(packet["strikes"]) == 1, "one strike, one row"
        cell = packet["grid"]["grid"][EXP_A]["450"]
        assert cell["call_gex"] > 0
        assert cell["put_gex"] < 0
        assert cell["gex"] == pytest.approx(cell["call_gex"] + cell["put_gex"])
        assert cell["sides_present"] == 2

    def test_same_strike_different_expiry_occupies_two_columns_not_one_cell(self):
        packet = project_triad_from_chain(
            adapter_payload(
                [
                    adapter_contract(expiry=EXP_A, oi=1000),
                    adapter_contract(expiry=EXP_B, oi=400),
                ]
            )
        )
        assert set(packet["grid"]["grid"]) == {EXP_A, EXP_B}
        assert packet["grid"]["grid"][EXP_A]["450"]["oi"] == 1000
        assert packet["grid"]["grid"][EXP_B]["450"]["oi"] == 400
        assert packet["strikes"][0]["expiries"] == [EXP_A, EXP_B]


class TestMissingnessIsNeverZero:
    def test_missing_oi_yields_null_not_zero(self):
        out = annotate_contract_exposure([adapter_contract(oi=None)], SPOT)[0]
        assert out["gex"] is None
        assert out["gex_reason"] == "OI_MISSING"
        assert out["gex_basis"] == "OI_UNKNOWN"

    def test_zero_oi_is_a_measurement_and_stays_zero(self):
        """The distinction that makes a zero meaningful."""
        out = annotate_contract_exposure([adapter_contract(oi=0)], SPOT)[0]
        assert out["gex"] == 0.0
        assert out["gex_reason"] is None
        assert out["gex_basis"] == "OI"

    def test_missing_gamma_yields_null_with_a_reason(self):
        out = annotate_contract_exposure([adapter_contract(gamma=None)], SPOT)[0]
        assert out["gex"] is None
        assert out["gex_reason"] == "GAMMA_MISSING"

    def test_unknown_option_type_is_not_assigned_a_sign(self):
        out = annotate_contract_exposure([adapter_contract(type="future")], SPOT)[0]
        assert out["gex"] is None
        assert out["gex_reason"] == "TYPE_UNKNOWN"

    def test_a_partially_observed_cell_reports_a_labelled_subtotal(self):
        packet = project_triad_from_chain(
            adapter_payload(
                [
                    adapter_contract(oi=1000),
                    adapter_contract(oi=None, strike=455),
                ]
            )
        )
        assert packet["coverage"]["usable"] == 1
        assert packet["coverage"]["contracts_without_gex"] == 1
        assert packet["coverage"]["returned"] == 2

    def test_no_contracts_means_no_net_gex_not_zero(self):
        packet = project_triad_from_chain(adapter_payload([]))
        assert packet["nodes"]["net_gex"] is None
        assert packet["nodes"]["regime"] == "unknown"
        assert packet["strikes"] == []
        assert packet["grid"]["grid"] == {}


class TestNoFabricatedValues:
    def test_vix_and_change_are_not_invented(self):
        packet = project_triad_from_chain(adapter_payload([adapter_contract()]))
        assert packet["vix"] is None
        assert packet["change_pct"] is None

    def test_polarity_is_not_exposure_divided_by_spot(self):
        packet = project_triad_from_chain(adapter_payload([adapter_contract()]))
        assert packet["nodes"]["polarity_level"] is None
        assert packet["nodes"]["net_gex"] is not None

    def test_zero_gamma_root_is_not_inferred_from_adjacent_strikes(self):
        packet = project_triad_from_chain(
            adapter_payload(
                [
                    adapter_contract(strike=450, type="call", gamma=0.02),
                    adapter_contract(strike=455, type="put", gamma=0.02, oi=2000),
                ]
            )
        )
        assert packet["nodes"]["gamma_flip"] is None

    def test_a_contract_with_no_expiry_is_dropped_and_counted_never_dated(self):
        packet = project_triad_from_chain(
            adapter_payload([adapter_contract(), adapter_contract(expiry="")])
        )
        assert packet["coverage"]["dropped_no_expiry"] == 1
        assert set(packet["grid"]["grid"]) == {EXP_A}

    def test_invalid_strike_is_counted_not_signed(self):
        packet = project_triad_from_chain(
            adapter_payload(
                [
                    adapter_contract(strike=0),
                    adapter_contract(strike=None),
                    adapter_contract(strike=-5),
                ]
            )
        )
        assert packet["coverage"]["dropped_bad_strike"] == 3
        assert packet["strikes"] == []


class TestExpiryCountIsNotDte:
    def test_cap_selects_expirations_and_declares_the_drop(self):
        packet = project_triad_from_chain(
            adapter_payload(
                [
                    adapter_contract(expiry=EXP_A, strike=450),
                    adapter_contract(expiry=EXP_B, strike=455),
                ]
            ),
            expiry_count=1,
        )
        assert packet["expiries_used"] == [EXP_A]
        assert packet["coverage"]["expiries_available"] == 2
        assert packet["coverage"]["expiries_requested"] == 1
        assert packet["coverage"]["expiry_cap_applied"] is True
        assert packet["coverage"]["expiries_dropped_by_cap"] == 1
        assert packet["coverage"]["truncated"] is True

    def test_per_expiry_day_count_is_derivable_from_T_not_assumed(self):
        packet = project_triad_from_chain(
            adapter_payload([adapter_contract(T=1 / 365, oi=100)])
        )
        assert packet["strikes"][0]["gex"] is not None
        # The packet does not claim a DTE it did not receive as a label.
        assert "dte" not in packet["coverage"]


class TestMultiplierPolicyIsCanonical:
    """Regression guard for a real defect in this module.

    An earlier version of annotate_contract_exposure re-implemented the formula
    with a hardcoded multiplier of 100. The canonical resolver does not: it
    honours an explicit per-contract multiplier, and it QUARANTINES
    adjusted/nonstandard contracts (returns None, so the aggregate counts them
    invalid). The hardcoded version therefore produced a confidently wrong
    number for both cases. These tests are the ones that would have caught it.
    """

    def test_an_explicit_non_100_multiplier_is_honoured(self):
        row = adapter_contract(multiplier=1000, oi=100)
        out = annotate_contract_exposure([row], SPOT)[0]
        # gex = sign * (gamma * mult * S^2 * 0.01) * oi
        expected = 0.011 * 1000 * SPOT * SPOT * 0.01 * 100
        assert out["gex"] == pytest.approx(expected, rel=1e-12)
        # A hardcoded 100 would have produced 1/10th of this.
        assert out["gex"] != pytest.approx(expected / 10, rel=1e-6)

    def test_an_adjusted_contract_is_quarantined_not_scored_at_100(self):
        out = annotate_contract_exposure([adapter_contract(adjusted=True)], SPOT)[0]
        assert out["gex"] is None
        assert out["gex_reason"] == "CONTRACT_QUARANTINED"

    def test_a_nonstandard_contract_is_quarantined(self):
        out = annotate_contract_exposure([adapter_contract(nonstandard=True)], SPOT)[0]
        assert out["gex"] is None
        assert out["gex_reason"] == "CONTRACT_QUARANTINED"

    def test_a_quarantined_contract_contributes_nothing_to_the_net(self):
        payload = adapter_payload(
            [adapter_contract(oi=1000), adapter_contract(strike=455, adjusted=True)]
        )
        packet = project_triad_from_chain(payload)
        assert packet["coverage"]["usable"] == 1
        assert packet["coverage"]["contracts_without_gex"] == 1

    def test_parity_holds_for_nonstandard_contracts_too(self):
        """The parity claim must cover the cases where it is easiest to break."""
        contracts = [
            adapter_contract(multiplier=1000),
            adapter_contract(type="put", multiplier=50, oi=700, strike=460),
            adapter_contract(strike=455, adjusted=True),
            adapter_contract(strike=465, oi=0),
        ]
        result = exposure_parity(contracts, SPOT)
        assert result["agrees"], (
            f"projection {result['projected_net']} != canonical {result['canonical_net']}"
        )


class TestSameDefinitionAcrossInstruments:
    """C4: one definition, applied to every supported instrument.

    Raw gross/net OI gamma must mean the same thing, in the same units, on the
    same basis, for an ETF, an index option chain and a single stock. If the
    formula varied by instrument, two panels showing "net GEX" would not be
    comparable, which is the failure this guards.
    """

    INSTRUMENTS = [
        ("SPY", "EQUITY", 450.0),
        ("QQQ", "EQUITY", 480.0),
        ("^SPX", "UNDERLYING_SECURITY_FOR_INDEX_OPTION", 5700.0),
        ("AAPL", "EQUITY", 230.0),
    ]

    @pytest.mark.parametrize("ticker,instrument,spot", INSTRUMENTS)
    def test_parity_holds_for_each_supported_instrument(self, ticker, instrument, spot):
        from services.public_api import resolve_public_instrument_type

        assert resolve_public_instrument_type(ticker, "chain") == instrument
        contracts = [
            adapter_contract(strike=spot, oi=1000, gamma=0.011, series=ticker.lstrip("^")),
            adapter_contract(strike=spot, type="put", oi=600, gamma=0.011),
            adapter_contract(strike=spot * 1.02, oi=250, expiry=EXP_B),
        ]
        result = exposure_parity(contracts, spot)
        assert result["agrees"], f"{ticker}: {result}"

    @pytest.mark.parametrize("ticker,instrument,spot", INSTRUMENTS)
    def test_formula_units_and_basis_are_instrument_independent(self, ticker, instrument, spot):
        packet = project_triad_from_chain(
            {
                "ticker": ticker,
                "spot": spot,
                "contracts": [adapter_contract(strike=spot, oi=1000, gamma=0.011)],
                "data_source": "public_api",
            }
        )
        assert packet["formula_version"] == "gex.v2", "the registry version is not per-instrument"
        assert "gex_net_v1" in packet["metric_ids"]
        for row in packet["strikes"]:
            assert row["gex"] is not None

    def test_an_instrument_with_no_coverage_is_unavailable_not_a_zero(self):
        """Gated by coverage: absent data must not render as a flat panel."""
        for ticker, _instrument, spot in self.INSTRUMENTS:
            packet = project_triad_from_chain(
                {"ticker": ticker, "spot": spot, "contracts": [], "data_source": "public_api"}
            )
            assert packet["nodes"]["net_gex"] is None, ticker
            assert packet["strikes"] == [], ticker
            assert packet["nodes"]["king"] is None, ticker

    def test_the_projection_does_not_branch_on_instrument_type(self):
        """Structural: instrument identity must not select a different formula.

        If a future change made SPX use a different multiplier or sign
        convention, this fails -- two panels would stop being comparable.
        """
        import inspect

        from services import triad_projection

        source = inspect.getsource(triad_projection.annotate_contract_exposure)
        for branchy in ("SPX", "EQUITY", "INDEX", "resolve_public_instrument_type"):
            assert branchy not in source, (
                f"annotate_contract_exposure must not branch on {branchy}; "
                "instrument handling belongs to the adapter, not the metric"
            )


def test_spot_is_required_for_exposure_and_its_absence_is_reported():
    out = annotate_contract_exposure([adapter_contract()], 0.0)[0]
    assert out["gex"] is None
    assert out["gex_reason"] == "SPOT_UNKNOWN"


def test_negative_gamma_is_rejected_rather_than_producing_a_flipping_sign():
    out = annotate_contract_exposure([adapter_contract(gamma=-0.01)], SPOT)[0]
    assert out["gex"] is None
    assert out["gex_reason"] == "GAMMA_NEGATIVE"


def test_annotate_does_not_mutate_its_input():
    row = adapter_contract()
    before = dict(row)
    annotate_contract_exposure([row], SPOT)
    assert row == before, "the adapter's own rows must not be rewritten in place"
