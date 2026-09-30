"""Frozen WallDeskSnapshot.v1 projection checks: source input to expected packet.

Unknown stays unknown: the missing-delta contract contributes to raw but is
excluded from delta-weighted totals and is listed under coverage/reasons.
Stale quotes are labeled, not promoted to current. Window activity uses only
comparable cumulative volume observations and exposes its actual interval.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.wall_desk_snapshot import (  # noqa: E402
    project_packet,
    project_window,
)
from tests.fixtures.wall_desk_fixture_v1 import (  # noqa: E402
    EXPECTED_PACKET_T0,
    EXPECTED_WINDOW_T0_T1,
    SOURCE_OBSERVATION_T0,
    SOURCE_OBSERVATION_T1,
)


def source_pair():
    return SOURCE_OBSERVATION_T0, SOURCE_OBSERVATION_T1


def expected_packet():
    return dict(EXPECTED_PACKET_T0)


def expected_window():
    return dict(EXPECTED_WINDOW_T0_T1)


def test_source_input_projects_to_expected_packet():
    first, _ = source_pair()
    packet = project_packet(first, "fixture-t0")
    want = expected_packet()
    for key in (
        "snapshot_id",
        "wall_id",
        "units",
        "raw_gross",
        "raw_net",
        "delta_gross",
        "delta_net",
        "delta_missing",
        "volume_gross_like",
        "volume_net",
    ):
        assert packet[key] == want[key]
    assert packet["coverage"] == want["coverage"]
    assert packet["reason_codes"] == want["reason_codes"]
    assert packet["snapshot_version"] == "WallDeskSnapshot.v1"
    assert packet["formula_version"] == "gex.v2"
    json.dumps(packet, allow_nan=False)


def test_window_activity_uses_comparable_observations_and_interval():
    first, second = source_pair()
    window = project_window(first, second)
    want = expected_window()
    assert window["window_gross_like"] == want["window_gross_like"]
    assert window["window_net"] == want["window_net"]
    assert window["interval"] == want["interval"]
    json.dumps(window, allow_nan=False)


def test_second_observation_does_not_rewrite_first_packet():
    first, second = source_pair()
    before = project_packet(first, "fixture-t0")
    _ = project_packet(second, "fixture-t1")
    after = project_packet(first, "fixture-t0")
    assert before == after
