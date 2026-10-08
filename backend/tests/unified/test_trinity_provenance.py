"""Trinity gamma-imbalance/spillover provenance (U12): failed-first counterexamples.

The published route must never pass one constant ADV for every ticker, and must
never reuse the selected ticker's gamma imbalance as the SPX input. With no
independently qualified, separately timestamped evidence the fields must carry
a typed unavailable/partial status instead of invented numbers.

All evidence is injected; no provider/upstream calls are made.
"""
import pytest

import routes.trinity as trinity


def _synthetic_chain():
    return {
        "spot": 100.0,
        "contracts": [
            {"strike": 95, "right": "call", "gamma": 0.10, "oi": 100, "iv": 0.2},
            {"strike": 105, "right": "put", "gamma": 0.10, "oi": 100, "iv": 0.2},
        ],
    }


def _fake_gex():
    def compute_gex_by_strike(spot, contracts, *args, **kwargs):
        return [
            {"strike": 95, "gex": 5_000_000.0},
            {"strike": 105, "gex": -2_000_000.0},
        ]
    return compute_gex_by_strike


@pytest.fixture
def injected(monkeypatch):
    calls = []

    async def fake_fetch(ticker, expiries=4):
        calls.append(ticker)
        return _synthetic_chain()

    monkeypatch.setattr(trinity, "_fetch_chain", fake_fetch)
    import services.gex_core as gex_core
    monkeypatch.setattr(gex_core, "compute_gex_by_strike", _fake_gex())
    return calls


def _adv_probe(result):
    """ADV the route actually used, recovered from the returned payload."""
    gi = result["gamma_imbalance"]
    return gi.get("adv_shares"), gi


@pytest.mark.asyncio
async def test_same_constant_adv_is_not_served_to_distinct_tickers(injected):
    """Counterexample 1: SPY and IWM must not be dosed with one shared 75M ADV."""
    spy = await trinity.get_trinity_for_ticker("SPY", 4)
    iwm = await trinity.get_trinity_for_ticker("IWM", 4)
    adv_spy, _ = _adv_probe(spy)
    adv_iwm, _ = _adv_probe(iwm)
    # With no qualified per-ticker ADV evidence, both must be typed unavailable.
    for adv, name in ((adv_spy, "SPY"), (adv_iwm, "IWM")):
        assert adv in (None, 0), f"{name} served an unqualified ADV: {adv}"
    # And a single shared constant can never appear for two different tickers.
    if adv_spy and adv_iwm:
        assert adv_spy != adv_iwm or (
            spy["gamma_imbalance"].get("adv_source") is not None
        )


@pytest.mark.asyncio
async def test_gamma_imbalance_typed_unavailable_without_qualified_adv(injected):
    """No 75M fallback: status must be explicit, regime must not claim a measurement."""
    result = await trinity.get_trinity_for_ticker("SPY", 4)
    gi = result["gamma_imbalance"]
    assert gi.get("status") == "unavailable"
    assert gi.get("reason") == "no_qualified_adv"
    assert gi.get("gamma_imbalance_pct") is None
    assert gi.get("regime") is None


@pytest.mark.asyncio
async def test_spillover_never_substitutes_selected_for_spx(injected):
    """Counterexample 2: passing the selected ticker's GI as the SPX input is refusal."""
    result = await trinity.get_trinity_for_ticker("SPY", 4)
    spill = result["cross_asset_spillover"]
    assert spill.get("status") == "unavailable"
    assert spill.get("reason") == "no_separate_spx_measurement"
    # The old defect passed the same value for both inputs behind the scenes;
    # a repaired surface must not expose a numeric spillover from that path.
    assert spill.get("spillover_risk") is None
    assert spill.get("index_driver_pct") is None


@pytest.mark.asyncio
async def test_constituent_failure_is_partial_not_silent(injected, monkeypatch):
    """A failing metric must surface a typed partial availability, not vanish silently."""
    import services.gex_paper_accurate as gpa

    def boom(*args, **kwargs):
        raise RuntimeError("injected constituent failure")

    # A qualified ADV exists, but the metric itself fails: typed partial, not silent.
    monkeypatch.setattr(trinity, "_qualified_adv_shares",
                        lambda ticker, raw: (50_000_000, {"source": "injected_test"}))
    monkeypatch.setattr(gpa, "compute_gamma_imbalance", boom)
    result = await trinity.get_trinity_for_ticker("SPY", 4)
    gi = result["gamma_imbalance"]
    assert gi.get("status") == "partial"
    assert gi.get("reason") == "compute_failed"
    # The rest of the response must stay complete and honest.
    assert result["ticker"] == "SPY"
    assert result["spot"] == 100.0
    assert result["net_gex"] == 3_000_000.0
    assert result["zero_gamma_levels"]
