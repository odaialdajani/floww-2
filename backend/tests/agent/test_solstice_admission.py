"""Authoritative Solstice admission: surfaces/records, never client numbers."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from services.agent.contracts import request_spec
from services.agent.display_map import display_facts
from services.agent.reads import ResearchReads
from tests.agent.test_display_map import NOW, QUERY, _v2_raw, _v2_screen
from tests.offline_network import deny_external_network  # noqa: F401


def adjusted():
    raw = _v2_raw()
    raw["metrics"] = {
        "walls": [{"wall_id": "w1", "low": 99, "high": 101, "members": [100], "gross": 12, "net": 3}],
        "wall_metrics": {"w1": {"daddex_gross": 6, "daddex_net": 1.5, "daddex_usable": 1,
                                  "daddex_missing": 1, "daddex_invalid": 1}},
        "grids": {"delta": {"strikes": [95, 100, 105], "expiries": ["2026-09-18"],
                              "grid": {"2026-09-18": {"95": -2, "100": 1.5, "105": 0}},
                              "formula_version": "gex.v2", "exposure_basis": "OI_DELTA_WEIGHTED",
                              "cell_missing_delta": {"2026-09-18": {"100": 1}},
                              "cell_invalid_delta": {"2026-09-18": {"100": 1}}, "status": "partial"}},
        "surface_coverage": {"delta": {"metric_id": "dadgex_net_v1", "basis": "OI_DELTA_WEIGHTED",
                                        "status": "partial", "usable": 3, "missing_delta": 1, "invalid_delta": 1}},
    }
    return raw


def screen(**changes):
    return _v2_screen(activePane="delta", overlayMetric="delta", selectedWall="w1",
                      selectedStrike=100, selectedExpiry="2026-09-18", **changes)


def values(facts):
    return {f["metric"]: f["value"] for f in facts}


def test_v2_adjusted_request_is_admitted_but_legacy_and_unknown_contexts_are_not():
    spec = request_spec({"question": "Why this wall?", "screen": screen()})
    assert spec["screen"]["overlayMetric"] == "delta"
    for bad in ({"ticker": "SPY", "overlayMetric": "delta"},
                {**screen(), "overlayMetric": "invented"},
                {**screen(), "displayMode": "price-history"}):
        with pytest.raises(ValueError):
            request_spec({"question": "Why this wall?", "screen": bad})


def test_same_wall_adjusted_values_and_partial_profile_keep_measured_zero_and_counts():
    facts, gaps = display_facts(adjusted(), {**screen(), "selectedValue": 99999}, "SPY", NOW)
    v = values(facts)
    assert v["Selected display cell"] == 1.5
    assert v["Displayed signed profile"] == [-2, 1.5, 0]
    assert v["Displayed profile missing delta"] == [0, 1, 0]
    assert v["Displayed profile invalid delta"] == [0, 1, 0]
    assert v["Selected raw wall gross"] == 12
    assert v["Selected adjusted wall net"] == 1.5
    assert v["Display basis"] == "OI_DELTA_WEIGHTED"
    assert any("partial" in g.lower() for g in gaps)
    assert next(f for f in facts if f["metric"] == "Selected display cell")["unit"] == "USD/1% move"


@pytest.mark.parametrize("change", [
    {"activePane": "raw"}, {"metric": "vex"}, {"mapStrikes": [999]},
    {"selectedWall": "other"}, {"selectedExpiry": "2026-10-01"},
    {"snapshotId": "other"}, {"provider": "other"}, {"formula": "other"},
])
def test_adjusted_conflicts_withhold_all_display_facts(change):
    facts, gaps = display_facts(adjusted(), {**screen(), **change}, "SPY", NOW)
    assert facts == [] and gaps


def test_live_adjusted_selection_cannot_switch_to_a_different_question_symbol():
    with pytest.raises(ValueError, match="displayed|selected"):
        request_spec({"question": "What about $QQQ?", "screen": screen()})


def test_raw_metric_pane_conflict_withholds_facts():
    raw = _v2_raw()
    raw["grid"]["vex_grid"] = {"2026-09-18": {"95": 1, "100": 2, "105": 3}}
    facts, gaps = display_facts(raw, _v2_screen(metric="vex", activePane="charm"), "SPY", NOW)
    assert facts == [] and gaps


def test_absent_adjusted_surface_is_never_replaced_by_raw():
    raw = adjusted()
    del raw["metrics"]["grids"]["delta"]
    facts, gaps = display_facts(raw, screen(), "SPY", NOW)
    assert facts == [] and gaps


def test_basis_is_part_of_evidence_identity():
    raw = adjusted()
    raw["metrics"]["grids"]["activity"] = {**deepcopy(raw["metrics"]["grids"]["delta"]), "exposure_basis": "VOLUME"}
    a, _ = display_facts(raw, screen(), "SPY", NOW)
    b, _ = display_facts(raw, {**screen(), "overlayMetric": "activity"}, "SPY", NOW)
    assert a and b and a[0]["snapshot_id"] != b[0]["snapshot_id"]


@pytest.mark.asyncio
async def test_adjusted_read_is_map_only_not_an_unrelated_chain_answer():
    forbidden = Mock(side_effect=AssertionError("Adjusted display tried an unrelated source"))
    reads = ResearchReads(forbidden, Mock(return_value=adjusted()), forbidden, read_daily_bars=forbidden)
    snap = await reads.snapshot("SPY", "all", screen=screen(), now=NOW)
    forbidden.assert_not_called()
    assert values(snap["facts"])["Selected adjusted wall net"] == 1.5


@pytest.mark.asyncio
async def test_replay_read_never_calls_chain_live_map_alerts_or_daily_bars():
    raw = adjusted()
    raw["replay"] = True
    raw["recorded_snapshot_id"] = "snap1"
    forbidden = Mock(side_effect=AssertionError("Replay tried a live source"))
    record = Mock(return_value=raw)
    reads = ResearchReads(forbidden, forbidden, forbidden, read_daily_bars=forbidden, read_recorded_map=record)
    snap = await reads.snapshot("SPY", "all", screen=screen(displayMode="replay"), now=NOW)
    record.assert_called_once_with("SPY", "snap1")
    forbidden.assert_not_called()
    assert values(snap["facts"])["Selected display cell"] == 1.5
    assert all(f["horizon"].startswith(("display:", "map:")) for f in snap["facts"])
    assert any("recorded" in g.lower() for g in snap["gaps"])


@pytest.mark.asyncio
async def test_missing_replay_record_has_only_explicit_gap_no_live_substitution():
    forbidden = Mock(side_effect=AssertionError("Replay tried a live source"))
    reads = ResearchReads(forbidden, forbidden, forbidden)
    snap = await reads.snapshot("SPY", "all", screen=screen(displayMode="replay"), now=NOW)
    forbidden.assert_not_called()
    assert snap["facts"] == [] and any("recorded" in g.lower() for g in snap["gaps"])


@pytest.mark.asyncio
async def test_replay_changed_question_is_saved_without_live_history_watch_or_model():
    import asyncio
    import time
    import uuid
    from unittest.mock import AsyncMock

    mongomock_motor = pytest.importorskip("mongomock_motor", reason="mongo mock needed for repository replay test")
    AsyncMongoMockClient = mongomock_motor.AsyncMongoMockClient

    from services.agent.repository import AgentRepository
    from services.agent.research import ResearchService

    raw = adjusted()
    raw.update(replay=True, recorded_snapshot_id="snap1")
    forbidden = Mock(side_effect=AssertionError("Replay tried live work"))
    record = Mock(return_value=raw)
    repo = AgentRepository(AsyncMongoMockClient(tz_aware=True).test)
    await repo.initialize()
    owner, _ = await repo.session()
    repo.watch_observations = AsyncMock(side_effect=AssertionError("Replay started a live watch"))
    model = Mock()
    model.once = AsyncMock(side_effect=AssertionError("Replay tried a model"))
    # No settings capability: this deterministic record needs no provider.
    del model.settings_for
    service = ResearchService(repo, ResearchReads(forbidden, forbidden, forbidden, read_recorded_map=record), model=model)
    spec = request_spec({"question": "What changed?", "screen": screen(displayMode="replay")})
    turn = await service.ask(owner, f"{int(time.time() * 1000)}-{uuid.uuid4()}", spec)
    await asyncio.gather(*service.tasks.values())
    saved = await repo.read(owner, turn["turn_id"])
    assert saved["status"] == "completed"
    assert values(saved["answer"]["facts"])["Selected display cell"] == 1.5
    assert "Recorded snapshot" in saved["answer"]["summary"]
    record.assert_called_once_with("SPY", "snap1")
    forbidden.assert_not_called()
    repo.watch_observations.assert_not_called()
    model.once.assert_not_called()


def test_replay_request_cannot_override_symbol_or_expiry_with_live_question():
    with pytest.raises(ValueError, match="recorded|Replay"):
        request_spec({"question": "What about $QQQ?", "screen": screen(displayMode="replay")})
    with pytest.raises(ValueError, match="recorded|Replay"):
        request_spec({"question": "SPY expiry 2026-10-16", "screen": screen(displayMode="replay")})
