"""Real calculator results and refusal boundaries for the first research slice."""

import copy
import math
from datetime import UTC, datetime, timedelta

import pytest

from bs_greeks import bs_charm, bs_gamma, bs_vanna
from services.agent.reads import ResearchReads

NOW = datetime(2026, 9, 11, 15, tzinfo=UTC)
# Deliberately not an exchange-close default: only this supplied instant counts.
EXPIRY = datetime(2026, 9, 11, 18, 37, tzinfo=UTC)


def chain():
    return dict(spot=100.0, data_source="public_api", event_time=NOW.isoformat(),
                fetched_at=NOW.isoformat(), spot_source="public-mid", spot_event_time=NOW.isoformat(),
                contracts=[dict(strike=100.0, expiry="2026-09-11", expiry_instant=EXPIRY.isoformat(),
                                type=kind, oi=oi, gamma=.01, iv=.2, T=1/365)
                           for kind, oi in (("call", 30), ("put", 10))])


async def snapshot(raw=None, *, bars=None, **kwargs):
    reads = ResearchReads(lambda *_: raw if raw is not None else chain(), lambda *_: None, lambda *_: [],
                          read_daily_bars=(lambda *_: bars) if bars is not None else None)
    return await reads.snapshot("SPY", "all", now=NOW, **kwargs)


def values(snap):
    return {f["metric"]: f for f in snap["facts"]}


@pytest.mark.asyncio
async def test_combined_real_calculator_units_and_exact_remaining_time():
    found = values(await snapshot())
    years = (EXPIRY - NOW).total_seconds() / (365 * 86400)
    # Independent per-contract scaling, not a second call to the aggregate.
    gamma = bs_gamma(100, 100, years, .2, q=.013)
    vanna = bs_vanna(100, 100, years, .2, q=.013)
    charm_call = bs_charm(100, 100, years, .2, q=.013, kind="call")
    charm_put = bs_charm(100, 100, years, .2, q=.013, kind="put")
    expected = {"gamma": gamma * 20 * 100 * 100**2 * .01,
                "vanna": vanna * 20 * 100 * 100 * .01,
                "charm": (charm_call * 30 - charm_put * 10) * 100 * 100 * .01}
    assert found["Model exposure strikes"]["value"] == [100]
    for name, result in expected.items():
        assert result != 0
        f = found[f"Total model {name} exposure"]
        assert f["value"] == pytest.approx(result, rel=1e-10)
        assert f["status"] == "ok"
        assert f["parents"] and all(p in {f["id"] for f in found.values()} for p in f["parents"])
    assert "platform vanna scale" in found["Total model vanna exposure"]["unit"]
    assert "platform charm scale" in found["Total model charm exposure"]["unit"]
    assert found["Implied move remaining years"]["value"] == pytest.approx(years)
    assert found["Implied move remaining years"]["value"] < 1/365
    assert found["Implied move estimate"]["value"] == round(.8 * 100 * .2 * math.sqrt(years), 2)
    assert found["Implied move expiry instant"]["value"] == EXPIRY.isoformat()


@pytest.mark.asyncio
async def test_actual_air_pocket_signature_and_nonempty_geometry():
    raw = chain()
    raw["contracts"] = [dict(strike=float(k), expiry="2026-09-11", type="call", gamma=1,
                             oi=1 if k in (99, 100) else 100) for k in range(96, 105)]
    found = values(await snapshot(raw))
    assert found["Estimated air pocket lower bounds"]["value"] == [99]
    assert found["Estimated air pocket upper bounds"]["value"] == [100]
    assert found["Nearest exposure level below"]["value"] == 99
    assert found["Nearest exposure level above"]["value"] == 101


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["no_cutoff", "naive_cutoff", "wrong_date", "expired", "no_iv", "bad_iv_time"])
async def test_no_guessed_expiry_or_iv(mutation):
    raw = chain()
    for c in raw["contracts"]:
        if mutation == "no_cutoff":
            del c["expiry_instant"]
        elif mutation == "naive_cutoff":
            c["expiry_instant"] = "2026-09-11T18:37:00"
        elif mutation == "wrong_date":
            c["expiry_instant"] = "2026-09-12T18:37:00+00:00"
        elif mutation == "expired":
            c["expiry_instant"] = (NOW - timedelta(seconds=1)).isoformat()
        elif mutation == "no_iv":
            c["iv"] = None
        else:
            c["iv_event_time"] = None
    snap = await snapshot(raw)
    assert "Total model vanna exposure" not in values(snap)
    assert "Implied move estimate" not in values(snap)
    assert any("explicit product expiry" in g or "explicit expiry" in g for g in snap["gaps"])
    # Provider-supplied gamma remains a separately labelled saved estimate.
    assert values(snap)["Total estimated gamma exposure"]["value"] == 2000


@pytest.mark.asyncio
async def test_unknown_and_stale_provenance_never_upgraded():
    raw = chain()
    raw["event_time"] = None
    unknown = await snapshot(raw)
    assert "Total model vanna exposure" not in values(unknown)
    assert values(unknown)["Estimated air pocket lower bounds"]["status"] == "degraded"
    assert "Implied move estimate" not in values(unknown)
    raw["event_time"] = (NOW - timedelta(hours=1)).isoformat()
    stale = await snapshot(raw)
    assert values(stale)["Total model vanna exposure"]["status"] == "stale"
    assert "Implied move estimate" not in values(stale)


@pytest.mark.asyncio
async def test_partial_model_coverage_is_degraded_and_does_not_freshen_stale_price():
    raw = chain()
    del raw["contracts"][1]["expiry_instant"]
    snap = await snapshot(raw)
    assert values(snap)["Total model vanna exposure"]["status"] == "degraded"
    assert any("excludes contracts" in g for g in snap["gaps"])
    raw["spot_event_time"] = (NOW - timedelta(hours=1)).isoformat()
    assert values(await snapshot(raw))["Total model vanna exposure"]["status"] == "stale"


@pytest.mark.asyncio
async def test_selected_expiry_does_not_reuse_a_valid_neighbor():
    raw = chain()
    other = copy.deepcopy(raw["contracts"])
    for c in other:
        c.update(expiry="2026-09-14", expiry_instant="2026-09-14T18:37:00+00:00", oi=99999)
    raw["contracts"].extend(other)
    one = await snapshot(raw, selected_expiry="2026-09-11")
    assert values(one)["Total estimated gamma exposure"]["value"] == 2000
    assert values(one)["Implied move expiry instant"]["value"] == EXPIRY.isoformat()
    absent = await snapshot(raw, selected_expiry="2026-09-18")
    assert "Implied move estimate" not in values(absent)
    assert "Total model gamma exposure" not in values(absent)


@pytest.mark.asyncio
async def test_different_expiry_pair_and_mismatched_instants_are_unavailable():
    raw = chain()
    raw["contracts"][1]["expiry"] = "2026-09-14"
    assert "Implied move estimate" not in values(await snapshot(raw))
    raw = chain()
    raw["contracts"][1]["expiry_instant"] = "2026-09-11T18:38:00+00:00"
    assert "Implied move estimate" not in values(await snapshot(raw))


def daily_bars():
    return dict(ticker="SPY", source="public_api", interval="1d", price_basis="unadjusted", complete=True,
                event_time="2026-09-10T20:00:00+00:00",
                bars=[dict(date=d, close=c) for d, c in zip(
                    ("2026-09-08", "2026-09-09", "2026-09-10"), (100, 110, 99), strict=True)])


@pytest.mark.asyncio
async def test_realized_volatility_uses_actual_close_estimator_with_hand_calculated_value():
    found = values(await snapshot(bars=daily_bars()))
    expected = abs(math.log(1.1) - math.log(.9)) / math.sqrt(2) * math.sqrt(252)
    rv = found["Realized daily close volatility"]
    assert rv["value"] == pytest.approx(expected)
    assert rv["value"] > 0 and rv["unit"] == "annualized fraction"
    assert rv["event_time"] == "2026-09-10T20:00:00+00:00"
    assert len(rv["parents"]) == 2
    assert found["Realized volatility close prices"]["value"] == [100, 110, 99]
    assert found["Realized volatility observation dates"]["value"] == ["2026-09-08", "2026-09-09", "2026-09-10"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["no_source", "no_basis", "wrong_ticker", "intraday", "missing_day", "duplicate",
                                      "reverse", "incomplete", "zero", "nan", "mixed_source", "mixed_basis", "future"])
async def test_realized_volatility_refuses_incoherent_history(mutation):
    bars = daily_bars()
    if mutation == "no_source":
        bars.pop("source")
    elif mutation == "no_basis":
        bars.pop("price_basis")
    elif mutation == "wrong_ticker":
        bars["ticker"] = "QQQ"
    elif mutation == "intraday":
        bars["interval"] = "1min"
    elif mutation == "missing_day":
        bars["bars"][0]["date"] = "2026-09-04"
    elif mutation == "duplicate":
        bars["bars"][0]["date"] = "2026-09-09"
    elif mutation == "reverse":
        bars["bars"].reverse()
    elif mutation == "incomplete":
        bars["complete"] = False
    elif mutation in {"zero", "nan"}:
        bars["bars"][1]["close"] = 0 if mutation == "zero" else float("nan")
    elif mutation == "mixed_source":
        bars["bars"][1]["source"] = "another_source"
    elif mutation == "mixed_basis":
        bars["bars"][1]["price_basis"] = "adjusted"
    else:
        bars["event_time"] = (NOW + timedelta(days=1)).isoformat()
    snap = await snapshot(bars=bars)
    assert "Realized daily close volatility" not in values(snap)
    assert any("Realized volatility is unavailable" in g for g in snap["gaps"])


@pytest.mark.asyncio
async def test_unknown_daily_source_time_stays_degraded():
    bars = daily_bars()
    bars["event_time"] = None
    rv = values(await snapshot(bars=bars))["Realized daily close volatility"]
    assert rv["status"] == "degraded" and rv["event_time"] is None


@pytest.mark.asyncio
async def test_price_only_never_reads_daily_bars_or_adds_capabilities():
    def prohibited(*_):
        raise AssertionError("price lookup must not read extras")

    reads = ResearchReads(lambda *_: chain(), prohibited, prohibited, read_daily_bars=prohibited)
    snap = await reads.snapshot("SPY", "all", now=NOW, price_only=True)
    assert [f["metric"] for f in snap["facts"]] == ["Underlying price"]
    assert not any("volatility" in g.lower() or "Combined" in g for g in snap["gaps"])


@pytest.mark.asyncio
async def test_daily_input_changes_snapshot_identity_and_is_not_mutated():
    bars = daily_bars()
    original = copy.deepcopy(bars)
    first = await snapshot(bars=bars)
    assert bars == original
    bars["bars"][1]["close"] = 105
    second = await snapshot(bars=bars)
    assert first["snapshot_id"] != second["snapshot_id"]
    assert values(first)["Realized daily close volatility"]["value"] != values(second)["Realized daily close volatility"]["value"]


@pytest.mark.asyncio
async def test_historical_daily_window_is_not_claimed_fresh():
    bars = daily_bars()
    for row, d in zip(bars["bars"], ("2026-09-03", "2026-09-04", "2026-09-08"), strict=True):
        row["date"] = d
    bars["event_time"] = "2026-09-08T20:00:00+00:00"
    assert values(await snapshot(bars=bars))["Realized daily close volatility"]["status"] == "stale"


@pytest.mark.asyncio
async def test_missing_provider_name_is_not_verified_input():
    raw = chain()
    del raw["data_source"]
    snap = await snapshot(raw)
    assert "Implied move estimate" not in values(snap)
    assert values(snap)["Total model vanna exposure"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_extreme_close_ratio_is_unavailable_instead_of_breaking_research():
    bars = daily_bars()
    bars["bars"][0]["close"] = 1e300
    bars["bars"][1]["close"] = 1e-300
    assert "Realized daily close volatility" not in values(await snapshot(bars=bars))


@pytest.mark.asyncio
async def test_calculator_failure_does_not_erase_other_verified_facts(monkeypatch):
    from services.agent import structure_reads, volatility_reads

    def failed(*_, **__):
        raise ValueError("calculation failed")

    monkeypatch.setattr(structure_reads, "compute_gex_by_strike", failed)
    monkeypatch.setattr(structure_reads, "calc_air_pockets", failed)
    monkeypatch.setattr(volatility_reads, "calc_implied_move", failed)
    monkeypatch.setattr(volatility_reads, "compute_realized_volatility", failed)
    snap = await snapshot(bars=daily_bars())
    found = values(snap)
    assert found["Underlying price"]["value"] == 100
    assert found["Total estimated gamma exposure"]["value"] == 2000
    assert "Total model vanna exposure" not in found
    assert "Implied move estimate" not in found
    assert "Realized daily close volatility" not in found


@pytest.mark.asyncio
async def test_large_series_is_bounded_without_inventing_missing_values():
    raw = chain()
    raw["contracts"] = [{**raw["contracts"][0], "strike": 90 + i / 25} for i in range(513)]
    snap = await snapshot(raw)
    found = values(snap)
    assert "Model exposure strikes" not in found
    assert "Model gamma exposure" not in found
    assert found["Total model gamma exposure"]["value"] > 0
    assert all(not isinstance(f["value"], list) or len(f["value"]) <= 512 for f in snap["facts"])
    assert any("series exceeds supported size" in g for g in snap["gaps"])


@pytest.mark.asyncio
async def test_future_iv_observation_is_not_reaged_to_chain_time():
    raw = chain()
    for contract in raw["contracts"]:
        contract["iv_event_time"] = (NOW + timedelta(seconds=90)).isoformat()
    found = values(await snapshot(raw))
    assert "Total model vanna exposure" not in found
    assert "Implied move estimate" not in found


@pytest.mark.asyncio
async def test_older_explicit_iv_time_is_preserved_as_an_actual_parent():
    raw = chain()
    observed = (NOW - timedelta(seconds=90)).isoformat()
    for contract in raw["contracts"]:
        contract["iv_event_time"] = observed
    found = values(await snapshot(raw))
    for name in ("Total model vanna exposure", "Implied move estimate"):
        item = found[name]
        assert item["event_time"] == observed
        assert item["status"] == "ok"
        parents = [f for f in found.values() if f["id"] in item["parents"]]
        assert any("implied volatility" in f["metric"].lower() and f["event_time"] == observed for f in parents)


@pytest.mark.asyncio
async def test_older_iv_cannot_borrow_a_barely_fresh_chain_timestamp():
    raw = chain()
    raw["event_time"] = raw["spot_event_time"] = (NOW - timedelta(seconds=899)).isoformat()
    observed = (NOW - timedelta(seconds=1018)).isoformat()
    for contract in raw["contracts"]:
        contract["iv_event_time"] = observed
    found = values(await snapshot(raw))
    assert "Implied move estimate" not in found
    assert found["Total model vanna exposure"]["status"] == "stale"
    assert found["Total model vanna exposure"]["event_time"] == observed


@pytest.mark.asyncio
async def test_unavailable_implied_move_distinguishes_present_inputs_from_missing_times():
    raw = chain()
    raw["event_time"] = None
    raw["spot_event_time"] = (NOW - timedelta(hours=1)).isoformat()
    for contract in raw["contracts"]:
        contract.pop("expiry_instant")
    snap = await snapshot(raw)
    gap = next(g for g in snap["gaps"] if g.startswith("Implied move is unavailable"))
    assert "saved underlying price is present (stale)" in gap
    assert "positive IV on 2 of 2 saved contracts" in gap
    assert "usable explicit future expiry time on 0 of 2" in gap
    assert "chain observation time is unknown" in gap
    assert "Implied move estimate" not in values(snap)


@pytest.mark.asyncio
async def test_unavailable_implied_move_does_not_claim_missing_iv_is_present():
    raw = chain()
    for contract in raw["contracts"]:
        contract["iv"] = None
    snap = await snapshot(raw)
    gap = next(g for g in snap["gaps"] if g.startswith("Implied move is unavailable"))
    assert "positive IV on 0 of 2 saved contracts" in gap
    assert "usable explicit future expiry time on 2 of 2" in gap
    assert "Implied move estimate" not in values(snap)
