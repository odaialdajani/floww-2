"""S3 wall-desk real contract (Spark).

Production must never import expected test output: domain.wall_desk_snapshot
no longer imports tests.fixtures (asserted statically). Missing spot means
unavailable, never 100. Cross-ticker windows are scope mismatches, never
differenced. Unknown option types and boolean volumes are skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain import wall_desk_snapshot as wds  # noqa: E402
from domain.wall_desk_snapshot import project_packet, project_window  # noqa: E402
from tests.fixtures.wall_desk_fixture_v1 import (  # noqa: E402
    SOURCE_OBSERVATION_T0,
)


def test_production_module_does_not_import_test_fixtures():
    src = Path(wds.__file__).read_text(encoding="utf-8")
    assert "tests.fixtures" not in src
    assert "tests/fixtures" not in src
    assert "EXPECTED_PACKET" not in src and "EXPECTED_WINDOW" not in src
    for name in ("expected_packet", "expected_window", "source_pair"):
        assert not hasattr(wds, name), name


def test_missing_spot_is_unavailable_not_100():
    obs = dict(SOURCE_OBSERVATION_T0)
    obs.pop("spot", None)
    obs["ticker"] = "QQQ"
    packet = project_packet(obs, "qqq-no-spot")
    assert packet["status"] == "unavailable"
    assert packet["reason"] == "SPOT_UNKNOWN"
    assert packet["spot"] is None
    assert packet["raw_gross"] is None and packet["delta_net"] is None
    assert packet["reason_codes"] == ["SPOT_UNKNOWN"]


def test_fixture_still_projects_with_real_wall_identity():
    packet = project_packet(SOURCE_OBSERVATION_T0, "fixture-t0")
    assert packet["status"] == "ok"
    assert packet["wall_id"] == "K100"  # from the observation, not invented
    assert packet["spot"] == 100.0
    assert packet["raw_gross"] == 3400.0 and packet["raw_net"] == 1400.0
    assert packet["metric_ids"][:5] == [
        "gex_gross_v1", "gex_net_v1", "dadgex_gross_v1", "dadgex_net_v1", "volume_gamma_v1",
    ]


def test_empty_contracts_packet_has_no_usable_values():
    obs = {"ticker": "SPY", "spot": 100.0, "wall_id": "K100", "contracts": []}
    packet = project_packet(obs, "empty")
    assert packet["status"] == "empty"
    assert packet["raw_gross"] == 0.0 and packet["raw_usable"] == 0


def test_cross_ticker_window_is_scope_mismatch():
    first = dict(SOURCE_OBSERVATION_T0, ticker="SPY")
    second = dict(SOURCE_OBSERVATION_T0, ticker="QQQ")
    window = project_window(first, second)
    assert window["status"] == "unavailable"
    assert window["reason"] == "SCOPE_MISMATCH"
    assert window["window_gross_like"] is None


def _window_obs(osi, volume, **kw):
    contract = {
        "osi": osi, "strike": 100.0, "type": "call", "gamma": 0.01,
        "delta": 0.5, "multiplier": 100.0, "volume": volume,
    }
    contract.update(kw)
    return {"ticker": "SPY", "spot": 100.0, "contracts": [contract]}


def test_window_skips_unknown_type_bool_volume_and_retraction():
    first = _window_obs("c1", 5)
    assert project_window(first, _window_obs("c1", 8))["window_net"] == 150.0
    unknown = project_window(first, _window_obs("c1", 8, type="mystery"))
    assert unknown["status"] == "unavailable"  # never default-put
    booled = project_window(first, _window_obs("c1", True))
    assert booled["status"] == "unavailable"  # True is not a volume
    retracted = project_window(_window_obs("c1", 8), _window_obs("c1", 5))
    assert retracted["status"] == "unavailable"
    assert retracted["reason"] == "NO_COMPARABLE_OBSERVATIONS"
    assert retracted["skipped_nonmonotonic"] == 1
