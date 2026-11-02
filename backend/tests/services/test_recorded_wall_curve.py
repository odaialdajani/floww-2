"""Recorded same-wall curve (`recorded-wall-curve.v1`).

One series owns one raw structural wall inside one declared scope. Every
point is a stored observation of that wall. Nothing is recomputed from a live
chain, nothing is forward-filled, no neighbouring wall is borrowed and a
signed exposure is never mistaken for a cumulative-volume correction.

These checks pin the refusals from `docs/RECORDED-PRODUCT-CONTRACTS.md`:
wall creation/removal, definition changes, session/scope/provider changes and
incomparable observations break the line; missing, invalid, unavailable and a
measured zero stay distinct.

Pure in-memory DuckDB reads: no app startup, no provider call, no write.
"""

import json
from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from services.heatmap_history import ensure_tables
from services.solstice_wall_curve import (
    CURVE_VERSION,
    REASON_COVERAGE_TRUNCATED,
    REASON_METRIC_NOT_STORED,
    REASON_METRIC_UNSUPPORTED,
    REASON_PROVIDER_CHANGED,
    REASON_SCOPE_CHANGED,
    REASON_SCOPE_UNVERIFIED,
    REASON_SESSION_ROLL,
    REASON_SOURCE_CLOCK_UNKNOWN,
    REASON_VALUE_UNAVAILABLE,
    REASON_WALL_DEFINITION_CHANGED,
    REASON_WALL_NOT_PRESENT,
    wall_curve,
)
from services.wall_structure import discover_walls

TICKER = "TST"
QUERY_KEY = "TST|4|day|None|False"
EXPIRIES = ["2030-01-19"]
SPOT = 500.0


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    ensure_tables(connection)
    yield connection
    connection.close()


def _iso(value: str) -> str:
    return datetime.fromisoformat(value).astimezone(UTC).isoformat()


def _wall(strikes=(500.0, 505.0, 510.0)):
    """A production wall record: real wall id, bounds and membership."""
    rows = [{"strike": strike, "gex": 1000.0} for strike in strikes]
    walls = discover_walls(rows, SPOT, scope={"symbol": TICKER, "formula": "gex.v2"})
    assert walls, "the fixture must produce one wall"
    return walls[0]


def _metric_entry(**overrides):
    entry = {
        "daddex_gross": 3000.0,
        "daddex_net": 1500.0,
        "daddex_usable": 3,
        "daddex_missing": 0,
        "daddex_invalid": 0,
        "volume_gross": 0.0,
        "volume_net": 0.0,
        "volume_usable": 0,
        "volume_missing": 0,
        "volume_invalid": 0,
        "session_delta_volume_gross": 0.0,
        "session_delta_volume_net": 0.0,
        "session_delta_volume_usable": 0,
        "session_delta_volume_missing": 0,
        "session_delta_volume_invalid": 0,
        "n_contracts": 3,
        "unreadable_strike": 0,
        "not_a_member": 0,
        "expiries": list(EXPIRIES),
    }
    entry.update(overrides)
    return entry


def _save(conn, snapshot_id, *, asof, received=None, walls, wall_metrics=None,
          metrics=True, event_time=None, query_key=QUERY_KEY, provider="public_api",
          expiries=None, formula="gex.v2", basis="OI", digest=None, coverage=None,
          quality=None):
    """Insert one stored observation the way the recorder stores it.

    The receipt clock defaults to one second before the availability clock, so
    the recorded order stays event <= receipt <= available.
    """
    expiries = list(EXPIRIES if expiries is None else expiries)
    if received is None:
        received = (datetime.fromisoformat(asof) - timedelta(seconds=1)).isoformat()
    metrics_payload = None
    if metrics:
        metrics_payload = {
            "walls": walls,
            "wall_metrics": wall_metrics or {},
        }
    conn.execute(
        "INSERT INTO heatmap_snapshots_v2 "
        "(snapshot_id,ticker,query_key,expiries,spot,data_source,exposure_basis,"
        "formula_version,asof_ts,received_at,n_contracts,n_usable,digest,"
        "strikes_json,walls_json,coverage_json,quality_json,metrics_full_json,"
        "context_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            snapshot_id,
            TICKER,
            query_key,
            json.dumps(expiries),
            SPOT,
            provider,
            basis,
            formula,
            asof,
            received,
            3,
            3,
            digest or f"digest-{snapshot_id}",
            json.dumps([{"strike": 500.0, "gex": 1000.0}]),
            json.dumps(walls),
            json.dumps(coverage or {"requested": 3, "returned": 3, "truncated": False}),
            json.dumps(quality or {"state": "clean", "reasonCodes": []}),
            json.dumps(metrics_payload) if metrics_payload is not None else None,
            json.dumps({"display": {"event_time": event_time or received,
                                    "map_query": query_key}}),
        ],
    )


def _curve(conn, wall_id, **kwargs):
    kwargs.setdefault("query_key", QUERY_KEY)
    return wall_curve(conn, TICKER, wall_id=wall_id, **kwargs)


def test_undeclared_scope_is_refused():
    wall = _wall()
    connection = duckdb.connect(":memory:")
    ensure_tables(connection)
    try:
        _save(connection, "obs-1", asof="2030-01-02T15:00:00+00:00",
              walls=[wall], wall_metrics={wall["wall_id"]: _metric_entry()})
        result = wall_curve(connection, TICKER, wall_id=wall["wall_id"])
        assert result["status"] == "history_unavailable"
        assert result["reason"] == REASON_SCOPE_UNVERIFIED
        assert result["points"] == []
    finally:
        connection.close()


def test_unsupported_metric_is_refused(conn):
    wall = _wall()
    result = _curve(conn, wall["wall_id"], metric_id="duo_d2gex_dS2_v1")
    assert result["status"] == "history_unavailable"
    assert result["reason"] == REASON_METRIC_UNSUPPORTED


def test_point_carries_identity_clocks_and_coverage(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:05+00:00",
          received="2030-01-02T15:00:02+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()},
          event_time="2030-01-02T10:00:00-05:00")

    result = _curve(conn, wall["wall_id"])
    assert result["version"] == CURVE_VERSION
    assert result["status"] == "ok"
    assert result["reason"] is None
    assert len(result["points"]) == 1

    point = result["points"][0]
    assert point["observation_id"] == "obs-1"
    assert point["content_digest"] == "digest-obs-1"
    assert point["clocks"]["event_time"] == _iso("2030-01-02T10:00:00-05:00")
    assert point["clocks"]["received_at"] == _iso("2030-01-02T15:00:02+00:00")
    assert point["clocks"]["available_at"] == _iso("2030-01-02T15:00:05+00:00")
    assert point["expiries"] == EXPIRIES
    assert point["scope"]["provider"] == "public_api"
    assert point["scope"]["query_key"] == QUERY_KEY
    assert point["scope"]["session_date"] == "2030-01-02"
    assert point["scope"]["exposure_basis"] == "OI"
    assert point["wall"]["wall_id"] == wall["wall_id"]
    assert point["wall"]["low"] == wall["low"]
    assert point["wall"]["high"] == wall["high"]
    assert point["wall"]["members"] == wall["members"]
    assert point["wall"]["definition_version"]
    assert point["metric"]["metric_id"] == "dadgex_net_v1"
    assert point["metric"]["units"] == "USD/1% move"
    assert point["metric"]["basis"] == "OI_DELTA_WEIGHTED"
    assert point["value"] == pytest.approx(1500.0)
    assert point["status"] == "ok"
    assert point["reason"] is None
    assert point["coverage"]["usable"] == 3
    assert point["coverage"]["missing"] == 0
    assert point["coverage"]["invalid"] == 0
    assert point["coverage"]["expiries"] == EXPIRIES

    series = result["series_key"]
    assert series["wall_id"] == wall["wall_id"]
    assert series["metric_id"] == "dadgex_net_v1"
    assert series["provider"] == "public_api"
    assert series["session_date"] == "2030-01-02"
    assert series["query_key"] == QUERY_KEY


def test_measured_zero_is_not_missing(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry(daddex_net=0.0)})

    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["value"] == 0.0
    assert point["status"] == "ok"
    assert point["reason"] is None


def test_missing_and_invalid_members_make_the_point_partial(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry(daddex_missing=1, daddex_invalid=1,
                                                      daddex_usable=1)})

    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["status"] == "partial"
    assert point["coverage"]["missing"] == 1
    assert point["coverage"]["invalid"] == 1
    assert point["value"] == pytest.approx(1500.0)


def test_unusable_population_is_unavailable_not_zero(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry(daddex_net=None, daddex_usable=0,
                                                      daddex_missing=3)})

    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["status"] == "unavailable"
    assert point["reason"] == REASON_VALUE_UNAVAILABLE
    assert point["value"] is None


def test_metric_not_stored_when_the_metrics_blob_is_absent(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall], metrics=False)

    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["status"] == "unavailable"
    assert point["reason"] == REASON_METRIC_NOT_STORED
    assert point["value"] is None


def test_absent_wall_is_an_explicit_gap_not_a_forward_fill(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})
    _save(conn, "obs-2", asof="2030-01-02T15:05:00+00:00", walls=[])

    result = _curve(conn, wall["wall_id"])
    assert len(result["points"]) == 1, "the removed wall must not be carried forward"
    assert result["points"][0]["observation_id"] == "obs-1"
    assert len(result["gaps"]) == 1
    gap = result["gaps"][0]
    assert gap["reason"] == REASON_WALL_NOT_PRESENT
    assert gap["after_observation_id"] == "obs-1"
    assert gap["before_observation_id"] == "obs-2"
    assert result["status"] == "partial"


def test_a_neighbouring_wall_is_never_joined(conn):
    wall = _wall()
    other = _wall(strikes=(520.0, 525.0))
    assert other["wall_id"] != wall["wall_id"]
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[other],
          wall_metrics={other["wall_id"]: _metric_entry(daddex_net=999.0)})

    result = _curve(conn, wall["wall_id"])
    assert result["points"] == [], "another wall's value is not this wall's point"
    assert result["gaps"][0]["reason"] == REASON_WALL_NOT_PRESENT
    assert result["status"] == "history_unavailable"
    assert result["reason"] == REASON_WALL_NOT_PRESENT


def test_changed_bounds_create_a_new_wall_id(conn):
    wall = _wall()
    moved = _wall(strikes=(500.0, 505.0))
    assert moved["wall_id"] != wall["wall_id"]
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})
    _save(conn, "obs-2", asof="2030-01-02T15:05:00+00:00", walls=[moved],
          wall_metrics={moved["wall_id"]: _metric_entry()})

    result = _curve(conn, wall["wall_id"])
    assert [point["observation_id"] for point in result["points"]] == ["obs-1"]
    assert result["gaps"][0]["reason"] == REASON_WALL_NOT_PRESENT


def test_definition_change_breaks_the_line(conn):
    wall = _wall()
    # Same wall id, different recorded membership: a definition change.
    changed = dict(wall)
    changed["members"] = list(wall["members"]) + [515.0]
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})
    _save(conn, "obs-2", asof="2030-01-02T15:05:00+00:00", walls=[changed],
          wall_metrics={wall["wall_id"]: _metric_entry()})

    result = _curve(conn, wall["wall_id"])
    assert len(result["points"]) == 2
    assert result["points"][0]["line"]["status"] == "continuous"
    assert result["points"][1]["line"]["status"] == "broken"
    assert result["points"][1]["line"]["break_reason"] == REASON_WALL_DEFINITION_CHANGED
    assert result["points"][0]["wall"]["definition_version"] != \
        result["points"][1]["wall"]["definition_version"]
    reasons = [gap["reason"] for gap in result["gaps"]]
    assert REASON_WALL_DEFINITION_CHANGED in reasons


def test_provider_change_breaks_the_line(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})
    _save(conn, "obs-2", asof="2030-01-02T15:05:00+00:00", walls=[wall],
          provider="vendor_feed", wall_metrics={wall["wall_id"]: _metric_entry()})

    result = _curve(conn, wall["wall_id"])
    reasons = [gap["reason"] for gap in result["gaps"]]
    assert REASON_PROVIDER_CHANGED in reasons
    assert result["points"][1]["line"]["break_reason"] == REASON_PROVIDER_CHANGED


def test_scope_change_breaks_the_line(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})
    _save(conn, "obs-2", asof="2030-01-02T15:05:00+00:00", walls=[wall],
          expiries=["2030-01-19", "2030-02-21"],
          wall_metrics={wall["wall_id"]: _metric_entry()})

    result = _curve(conn, wall["wall_id"])
    reasons = [gap["reason"] for gap in result["gaps"]]
    assert REASON_SCOPE_CHANGED in reasons
    assert result["points"][1]["line"]["break_reason"] == REASON_SCOPE_CHANGED


def test_session_roll_breaks_the_line(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-03T04:30:05+00:00", walls=[wall],
          event_time="2030-01-02T23:30:00-05:00",
          wall_metrics={wall["wall_id"]: _metric_entry()})
    _save(conn, "obs-2", asof="2030-01-03T14:30:05+00:00", walls=[wall],
          event_time="2030-01-03T09:30:00-05:00",
          wall_metrics={wall["wall_id"]: _metric_entry()})

    result = _curve(conn, wall["wall_id"])
    reasons = [gap["reason"] for gap in result["gaps"]]
    assert REASON_SESSION_ROLL in reasons
    assert result["points"][0]["scope"]["session_date"] == "2030-01-02"
    assert result["points"][1]["scope"]["session_date"] == "2030-01-03"


def test_late_receipt_is_excluded_by_the_cutoff(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})
    _save(conn, "obs-2", asof="2030-01-02T15:07:00+00:00",
          received="2030-01-02T15:06:30+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})

    result = _curve(conn, wall["wall_id"], as_of="2030-01-02T15:03:00+00:00")
    assert [point["observation_id"] for point in result["points"]] == ["obs-1"]

    # Without the cutoff the late observation is still a stored observation.
    full = _curve(conn, wall["wall_id"])
    assert [point["observation_id"] for point in full["points"]] == ["obs-1", "obs-2"]


def test_same_digest_at_two_observation_times_is_two_points(conn):
    wall = _wall()
    for snapshot_id, asof in (("obs-1", "2030-01-02T15:00:00+00:00"),
                              ("obs-2", "2030-01-02T15:05:00+00:00")):
        _save(conn, snapshot_id, asof=asof, walls=[wall],
              wall_metrics={wall["wall_id"]: _metric_entry()},
              digest="same-content-digest")

    result = _curve(conn, wall["wall_id"])
    assert len(result["points"]) == 2
    assert result["points"][0]["content_digest"] == "same-content-digest"
    assert result["points"][1]["content_digest"] == "same-content-digest"
    assert result["points"][0]["observation_id"] != result["points"][1]["observation_id"]
    assert result["points"][0]["clocks"]["available_at"] != \
        result["points"][1]["clocks"]["available_at"]


def test_truncated_coverage_is_partial(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()},
          coverage={"requested": 3, "returned": 1, "truncated": True})

    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["status"] == "partial"
    assert point["reason"] == REASON_COVERAGE_TRUNCATED
    assert point["coverage"]["snapshot_truncated"] is True


def test_session_day_uses_the_new_york_date(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T02:00:05+00:00",
          received="2030-01-02T02:00:02+00:00", walls=[wall],
          event_time="2030-01-01T21:00:00-05:00",
          wall_metrics={wall["wall_id"]: _metric_entry()})

    ny_day = _curve(conn, wall["wall_id"], day="2030-01-01")
    assert [point["observation_id"] for point in ny_day["points"]] == ["obs-1"]
    utc_day = _curve(conn, wall["wall_id"], day="2030-01-02")
    assert utc_day["points"] == []
    assert utc_day["status"] == "history_unavailable"


def test_negative_delta_weighted_session_exposure_is_not_a_volume_retraction(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry(
              session_delta_volume_net=-250.0,
              session_delta_volume_usable=2)})

    result = _curve(conn, wall["wall_id"], metric_id="session_delta_volume_gamma_v1")
    point = result["points"][0]
    assert point["value"] == pytest.approx(-250.0)
    assert point["metric"]["units"] == "USD/1% move"
    assert point["retraction"] is None
    assert point["retraction_reason"] == "NOT_A_VOLUME_CHANGE_METRIC"
    assert point["value"] != 0.0


@pytest.mark.parametrize("field,value", [
    ("daddex_missing", None), ("daddex_missing", False),
    ("daddex_invalid", -1), ("daddex_usable", 0.5),
    ("n_contracts", "unknown"), ("n_contracts", float("inf")),
    ("unreadable_strike", float("nan")), ("not_a_member", -1),
])
def test_unknown_or_invalid_coverage_never_becomes_complete_or_raises(conn, field, value):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry(**{field: value})})
    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["status"] == "unavailable"
    assert point["reason"] == "COVERAGE_UNVERIFIED"
    assert point["value"] is None
    json.dumps(point, allow_nan=False)


def test_malformed_stored_metric_entry_is_a_typed_gap(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: [123]})
    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["status"] == "unavailable"
    assert point["reason"] == "METRIC_INVALID"
    assert point["value"] is None


def test_partial_population_breaks_both_adjacent_curve_segments(conn):
    wall = _wall()
    for number, entry in enumerate([
        _metric_entry(), _metric_entry(daddex_usable=2, daddex_missing=1), _metric_entry(),
    ]):
        _save(conn, f"obs-{number}", asof=f"2030-01-02T15:{number * 5:02d}:00+00:00",
              walls=[wall], wall_metrics={wall["wall_id"]: entry})
    points = _curve(conn, wall["wall_id"])["points"]
    assert points[0]["line"]["status"] == "continuous"
    assert points[1]["status"] == "partial"
    assert points[1]["line"]["status"] == "broken"
    assert points[2]["line"]["status"] == "broken"
    assert points[1]["line"]["break_reason"] == "POPULATION_INCOMPLETE"
    assert points[2]["line"]["break_reason"] == "POPULATION_INCOMPLETE"


def test_unreadable_store_is_not_reported_as_empty_history():
    closed = duckdb.connect(":memory:")
    closed.close()
    result = _curve(closed, "recorded-wall")
    assert result["status"] == "history_unavailable"
    assert result["reason"] == "STORE_UNAVAILABLE"


def test_point_limit_discloses_omitted_recorded_observations(conn):
    wall = _wall()
    for number in range(2):
        _save(conn, f"obs-{number}", asof=f"2030-01-02T15:0{number}:00+00:00",
              walls=[wall], wall_metrics={wall["wall_id"]: _metric_entry()})
    result = _curve(conn, wall["wall_id"], limit=1)
    assert len(result["points"]) == 1
    assert result["status"] == "partial"
    assert result["reason"] == "RESULT_TRUNCATED"
    assert result["coverage"]["n_points_available"] == 2
    assert result["coverage"]["truncated"] is True


@pytest.mark.parametrize("scope", [{"provider": None}, {"formula": None}, {"basis": None}, {"expiries": []}])
def test_undeclared_stored_scope_cannot_produce_usable_curve_points(conn, scope):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()}, **scope)
    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["status"] == "unavailable"
    assert point["reason"] == "SCOPE_UNVERIFIED"
    assert point["value"] is None


@pytest.mark.parametrize("change", [{"members": []}, {"low": None}, {"high": float("inf")}, {"members": [float("nan")]}])
def test_unverifiable_wall_definition_stays_unavailable_and_serializable(conn, change):
    wall = {**_wall(), **change}
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})
    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["status"] == "unavailable"
    assert point["reason"] == "WALL_DEFINITION_UNVERIFIED"
    assert point["value"] is None
    json.dumps(point, allow_nan=False)


def test_unknown_event_clock_is_an_unavailable_point(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          event_time=None,
          wall_metrics={wall["wall_id"]: _metric_entry()})
    conn.execute("UPDATE heatmap_snapshots_v2 SET context_json = ? WHERE snapshot_id = ?",
                 [json.dumps({"display": {}}), "obs-1"])

    point = _curve(conn, wall["wall_id"])["points"][0]
    assert point["status"] == "unavailable"
    assert point["reason"] == REASON_SOURCE_CLOCK_UNKNOWN
    assert point["value"] is None


def test_limit_keeps_the_gaps_and_identity(conn):
    wall = _wall()
    _save(conn, "obs-1", asof="2030-01-02T15:00:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})
    _save(conn, "obs-2", asof="2030-01-02T15:05:00+00:00", walls=[], wall_metrics={})
    _save(conn, "obs-3", asof="2030-01-02T15:10:00+00:00", walls=[wall],
          wall_metrics={wall["wall_id"]: _metric_entry()})

    result = _curve(conn, wall["wall_id"], limit=1)
    assert len(result["points"]) == 1
    assert result["points"][0]["observation_id"] == "obs-1"
    assert result["gaps"], "a limit must not hide the recorded break"
