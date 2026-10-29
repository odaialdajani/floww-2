"""C2 producer-contract pins (Hermes-Architect, 2026-10-24, lane
backend-lane-20261023 at 43f2edc2, product parent 9b1d1179).

Pins the SERVED contract documented in
takeover-20261022/C2-PRODUCER-CONTRACTS-20261024.json so the Stock lane
(Hermes-1) can code against exact response shapes and every family's refusal
vocabulary without re-deriving them from source:

  * price-history response key sets with and without include_envelopes
    (the default must stay byte-stable: NO envelopes key);
  * the populated initial_balance envelope (bounds/coverage/certification)
    and the honest typed refusals of flow/delta/darkpool/naked at the same
    route, plus the no-valid-clock all-unavailable branch;
  * weekend-cursor refusals (cursor-not-in-regular-session) at unit level;
  * the shared row-gate vocabulary and the capability-not-declared rule;
  * the published NYSE session schedule the cursor rules depend on.

Synthetic bars only, in-process TestClient, in-memory/stubbed store access.
No provider, port, service or user data is touched. A passing pin is a
characterization of committed behavior, not independent acceptance.
"""
import sys
import types
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

NY = ZoneInfo("America/New_York")
FRIDAY = datetime(2026, 10, 23, 9, 30, tzinfo=NY)  # published trading day
FRIDAY_RECEIPT = datetime(2026, 10, 23, 10, 35, tzinfo=NY)
SATURDAY_RECEIPT = datetime(2026, 10, 24, 12, 0, tzinfo=NY)


def _synthetic_friday_bars(count=12):
    bars = []
    for i in range(count):
        t = FRIDAY + timedelta(minutes=5 * i)
        o = 580.0 + 0.5 * i
        bars.append({"t": t.isoformat(), "o": o, "h": o + 0.8, "l": o - 0.6,
                     "c": o + 0.3, "v": 1_000_000.0 + 1_000 * i})
    return bars


def _duckdb_engine_module(conn=None):
    """A services.duckdb_engine stand-in the real route bodies import."""
    stub = types.ModuleType("services.duckdb_engine")
    stub.db = types.SimpleNamespace() if conn is None else types.SimpleNamespace(conn=conn)
    return stub


def _client(monkeypatch, supplier):
    monkeypatch.setitem(sys.modules, "services.duckdb_engine", _duckdb_engine_module(None))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes import price_history
    monkeypatch.setattr(price_history, "_history_bars", supplier)
    app = FastAPI()
    app.include_router(price_history.router)
    return TestClient(app)


def _friday_supplier(bars=None, receipt=FRIDAY_RECEIPT):
    payload = _synthetic_friday_bars() if bars is None else bars

    async def supplier(ticker, period, aggregation, sessions, instrument_type="EQUITY"):
        return list(payload), None, receipt.isoformat()

    return supplier


DEFAULT_KEYS = {
    "ticker", "frames", "query_key", "scopes", "node_max_age_seconds",
    "candles", "candles_with_recorded_nodes", "node_coverage", "exposure_line",
    "cvd_line", "note", "price_status", "price_failure", "node_status",
    "records_truncated", "days", "prices_received_at", "last_candle_at",
    "bar_seconds", "price_sessions_returned", "recording", "contract_symbol",
    "contract_status", "contract_bars",
}
NO_CLOCK_KEYS = {
    "ticker", "frames", "query_key", "scopes", "node_max_age_seconds",
    "candles", "candles_with_recorded_nodes", "node_coverage", "exposure_line",
    "cvd_line", "note", "price_status", "node_status", "days", "recording",
    "price_failure", "prices_received_at", "contract_symbol",
    "contract_status", "contract_bars",
}
FRAME_KEYS = {
    "time", "open", "high", "low", "close", "session", "volume", "nodes",
    "snapshot_id", "nodes_known_at", "node_age_seconds", "end_time",
    "exposure_centre", "exposure_upper", "exposure_lower", "cvd",
    "cvd_delta", "duration_seconds",
}
ENVELOPE_KEYS = {"source_gaps", "session", "initial_balance", "flow", "naked", "delta", "darkpool"}
IB_AVAILABLE_KEYS = {"instrument", "session", "opening_minutes", "cursor", "bar_seconds",
                     "approximation", "certification", "coverage", "gaps", "status",
                     "bounds", "bars_used"}
FLOW_GAP_KEYS = {"malformed_row", "foreign_instrument", "late_receipt", "missing_receipt",
                 "previous_session", "future_event", "stale_event", "filtered_out"}
DARKPOOL_KEYS = {"ticker", "cursor", "bar_seconds", "window", "session", "instrument",
                 "admitted_count", "excluded_count", "gaps", "prints", "top",
                 "certification", "status", "reason"}


def test_route_contract_default_response_has_no_envelopes(monkeypatch):
    client = _client(monkeypatch, _friday_supplier())
    response = client.get("/api/heatseeker/price-history/SPY?days=1&interval_minutes=5")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == DEFAULT_KEYS
    assert "envelopes" not in body  # byte-stable default: opt-in only
    assert body["price_status"] == "available"
    assert body["price_failure"] is None
    assert body["bar_seconds"] == 300
    assert body["prices_received_at"] == FRIDAY_RECEIPT.isoformat()
    assert len(body["frames"]) == 12
    assert set(body["frames"][0]) == FRAME_KEYS
    assert body["frames"][0]["duration_seconds"] == 300
    assert all(frame["volume"] == 1_000_000.0 + 1_000 * i for i, frame in enumerate(body["frames"]))
    assert all("cvd" in frame and "cvd_delta" in frame for frame in body["frames"])


def test_route_contract_populated_initial_balance_and_typed_refusals(monkeypatch):
    client = _client(monkeypatch, _friday_supplier())
    response = client.get("/api/heatseeker/price-history/SPY"
                          "?days=1&interval_minutes=5&include_envelopes=true&opening_minutes=60")
    assert response.status_code == 200, response.text
    body = response.json()
    env = body["envelopes"]
    assert set(env) == ENVELOPE_KEYS
    assert env["source_gaps"] == {"malformed_bar_clock": 0, "invalid_or_duplicate_bars": 0}
    assert env["session"]["date"] == "2026-10-23"
    assert env["session"]["tz"] == "America/New_York"
    # The only family this supplier can populate today:
    ib = env["initial_balance"]
    assert set(ib) == IB_AVAILABLE_KEYS
    assert ib["status"] == "available"
    assert ib["coverage"] == {"covered": 12, "expected_total": 12, "complete": True,
                             "opening_minutes": 60}
    assert ib["bounds"]["low"] == pytest.approx(579.4)
    assert ib["bounds"]["high"] == pytest.approx(586.3)
    assert len(ib["bars_used"]) == 12
    assert ib["approximation"] == "bar-resolution"
    assert ib["certification"]["certified_by_hash"] is False
    # No production classified-tape/print/naked source exists: typed refusals.
    assert env["flow"]["status"] == "unavailable"
    assert env["flow"]["reason"] == "no admitted rows for this flow bucket"
    assert set(env["flow"]["gaps"]) == FLOW_GAP_KEYS
    assert all(value == 0 for value in env["flow"]["gaps"].values())
    assert env["delta"] == {"status": "refused", "reason": "capability-not-declared: classified_sizes"}
    assert env["darkpool"]["status"] == "unavailable"
    assert env["darkpool"]["reason"] == "no eligible dark-pool prints"
    assert env["naked"]["status"] == "not_requested"


def test_route_contract_no_valid_clocks_is_all_unavailable(monkeypatch):
    bad_bars = [{"t": "not-a-clock", "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5}]
    client = _client(monkeypatch, _friday_supplier(bars=bad_bars))
    response = client.get("/api/heatseeker/price-history/SPY"
                          "?days=1&interval_minutes=5&include_envelopes=true")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == NO_CLOCK_KEYS
    assert body["price_status"] == "unavailable"
    env = body.get("envelopes")  # early-return branch: no envelopes key at all
    assert env is None
    assert body["price_failure"] == {"reason": "invalid_price_bars", "retry_after_seconds": None}


def test_route_contract_rejects_off_grid_interval(monkeypatch):
    client = _client(monkeypatch, _friday_supplier())
    response = client.get("/api/heatseeker/price-history/SPY?days=1&interval_minutes=7")
    assert response.status_code == 422


def test_route_contract_weekend_receipt_names_every_gap(monkeypatch):
    client = _client(monkeypatch, _friday_supplier(receipt=SATURDAY_RECEIPT))
    response = client.get("/api/heatseeker/price-history/SPY"
                          "?days=1&interval_minutes=5&include_envelopes=true")
    assert response.status_code == 200, response.text
    env = response.json()["envelopes"]
    # Receipt's own day (Saturday) has no bars: never fabricate older-day availability.
    assert env["initial_balance"]["status"] == "not_requested"
    assert "older days" in env["initial_balance"]["reason"]
    assert env["flow"] == {"status": "refused", "reason": "cursor-not-in-regular-session"}
    assert env["darkpool"]["status"] == "refused"
    assert env["darkpool"]["reason"] == "cursor-not-in-regular-session"
    assert env["delta"]["status"] == "refused"
    assert env["delta"]["reason"] == "capability-not-declared: classified_sizes"


def test_initial_balance_refusal_vocabulary():
    from services.chart_profiles import admit_initial_balance

    def call(**overrides):
        kwargs = {"ticker": "SPY", "cursor": 1000.0, "session_date": "2026-10-23",
                  "opening_minutes": 60, "bar_seconds": 300,
                  "tick_size": 0.01, "units": "usd", "entitlement": "delayed-15m"}
        kwargs.update(overrides)
        bars = kwargs.pop("bars", [])
        return admit_initial_balance(bars, **kwargs)

    assert call(bar_seconds=120) == {"status": "refused", "reason": "unsupported-bar-seconds"}
    assert call(opening_minutes=7) == \
        {"status": "refused", "reason": "opening-duration-not-grid-divisible"}
    assert call(opening_minutes=0) == \
        {"status": "refused", "reason": "opening-duration-not-explicit"}
    assert call(opening_minutes=400) == \
        {"status": "refused", "reason": "opening-duration-exceeds-session"}
    assert call(session_date="2026-10-25") == \
        {"status": "refused", "reason": "unsupported-session-date"}
    # A cursor outside the selected session refuses before any coverage math.
    assert call() == {"status": "refused", "reason": "cursor-not-in-selected-session"}
    # The served route never passes allow_first_loaded_range, so a truncated
    # opening can never be renamed first-loaded-range over the wire.
    import inspect
    default = inspect.signature(admit_initial_balance).parameters["allow_first_loaded_range"].default
    assert default is False


def test_flow_bucket_gaps_and_cursor_seconds_contract():
    from services.chart_flow import admit_flow_bucket
    start = datetime.fromisoformat("2026-10-23T09:30:00-04:00").timestamp()
    cursor = start + 310.0
    env = admit_flow_bucket([], ticker="SPY", cursor=cursor, bar_seconds=300)
    assert set(env) >= {"status", "reason", "gaps", "cursor", "window", "bucket_index",
                        "totals", "scope_hash", "certification", "filters_applied"}
    assert env["status"] == "unavailable"
    assert env["reason"] == "no admitted rows for this flow bucket"
    assert set(env["gaps"]) == FLOW_GAP_KEYS
    assert env["cursor"] == pytest.approx(cursor)  # epoch SECONDS (frontend binds ms)
    # Weekend cursor refuses; unknown filters refuse; hash never certifies.
    weekend = admit_flow_bucket([], ticker="SPY", cursor=1730000000.0, bar_seconds=300)
    assert weekend == {"status": "refused", "reason": "cursor-not-in-regular-session"}
    assert admit_flow_bucket([], ticker="SPY", cursor=cursor, bar_seconds=300,
                             filters={"nope": 1}) == {"status": "refused",
                                                      "reason": "unsupported-filter"}


def test_flow_bucket_populated_totals_with_named_gaps():
    from services.chart_flow import admit_flow_bucket
    start = datetime.fromisoformat("2026-10-23T09:30:00-04:00").timestamp()
    cursor = start + 590.0  # inside bucket 1 and AFTER both events (receipt clock >= events)
    rows = [
        {"ticker": "SPY", "event_time": start + 300, "received_at": cursor - 1,
         "side": "call", "premium": 120.0},
        {"ticker": "SPY", "event_time": start + 400, "received_at": cursor - 1,
         "side": "put", "premium": 30.0},
        {"ticker": "QQQ", "event_time": start + 350, "received_at": cursor - 1,
         "side": "call", "premium": 999.0},  # foreign instrument: named gap
    ]
    env = admit_flow_bucket(rows, ticker="SPY", cursor=cursor, bar_seconds=300)
    assert env["status"] == "available"
    assert env["window"]["start"] == pytest.approx(start + 300)
    assert env["window"]["end"] == pytest.approx(start + 600)
    assert env["totals"]["call_premium"] == pytest.approx(120.0)
    assert env["totals"]["put_premium"] == pytest.approx(-30.0)
    assert env["totals"]["count"] == 2
    assert env["gaps"]["foreign_instrument"] == 1
    assert env["gaps"]["future_event"] == 0
    assert env["certification"]["certified_by_hash"] is False


def test_delta_capability_and_populated_shape():
    from services.chart_delta import admit_delta
    start = datetime.fromisoformat("2026-10-23T09:30:00-04:00").timestamp()
    cursor = start + 610.0
    base = {"ticker": "SPY", "cursor": cursor, "bar_seconds": 300,
            "tick_size": 0.01, "units": "usd", "entitlement": "delayed-15m"}
    # Capability is never defaulted: refusing to declare it refuses the read.
    assert admit_delta([], capabilities={}, **base) == \
        {"status": "refused", "reason": "capability-not-declared: classified_sizes"}
    assert admit_delta([], capabilities=None, **base) == \
        {"status": "refused", "reason": "capability-not-declared: classified_sizes"}
    bars = [
        {"ticker": "SPY", "event_time": start, "received_at": cursor - 1,
         "buy": 100.0, "sell": 40.0, "unclassified": 5.0},
        {"ticker": "SPY", "event_time": start + 300, "received_at": cursor - 1,
         "buy": 10.0, "sell": 20.0, "unclassified": 0.0},
    ]
    env = admit_delta(bars, capabilities={"classified_sizes": True}, **base)
    assert env["status"] == "available"
    assert [row["delta"] for row in env["rows"]] == [pytest.approx(60.0), pytest.approx(-10.0)]
    assert env["rows"][1]["open"] == pytest.approx(60.0)  # running session CVD
    assert env["totals"]["delta"] == pytest.approx(50.0)
    assert env["totals"]["classified_volume"] == pytest.approx(170.0)
    assert env["totals"]["unclassified_volume"] == pytest.approx(5.0)
    assert env["capabilities"] == {"classified_sizes": True}


def test_darkpool_contract_shapes():
    from services.chart_darkpool import admit_darkpool_prints
    start = datetime.fromisoformat("2026-10-23T09:30:00-04:00").timestamp()
    cursor = start + 310.0
    base = {"ticker": "SPY", "cursor": cursor, "bar_seconds": 300,
            "tick_size": 0.01, "units": "usd", "entitlement": "delayed-15m"}
    env = admit_darkpool_prints([], **base)
    assert set(env) == DARKPOOL_KEYS
    assert env["status"] == "unavailable"
    assert env["reason"] == "no eligible dark-pool prints"
    # Direction stays unknown even on a populated read; aggregates never pass.
    rows = [{"ticker": "SPY", "event_time": start + 300, "received_at": cursor - 1,
             "price": 100.0, "size": 500.0, "venue": "DARK", "delay_seconds": 30.0},
            {"ticker": "SPY", "event_time": start + 310, "received_at": cursor - 1,
             "price": 100.0, "size": 500.0, "venue": "DARK", "aggregate": True}]
    populated = admit_darkpool_prints(rows, top_n=3, **base)
    assert populated["status"] == "available"
    assert populated["admitted_count"] == 1
    assert populated["gaps"]["aggregated_row"] == 1
    assert populated["prints"][0]["direction"] == "unknown"
    assert populated["prints"][0]["notional"] == pytest.approx(50_000.0)


def test_naked_claim_never_certifies_unknown_range():
    from services.chart_profiles import naked_levels_claim
    start = datetime.fromisoformat("2026-10-23T09:30:00-04:00").timestamp()
    claim = naked_levels_claim([], [], cursor=start + 600, coverage=None)
    assert claim["status"] == "not-claimable"
    assert claim["reason"] == "unknown-range-cannot-certify-untouched"
    assert claim["claims"] == []


def test_published_nyse_schedule_pins():
    from services.chart_flow import session_bounds_for_date
    friday = session_bounds_for_date(datetime(2026, 10, 23).date())
    assert friday["date"] == "2026-10-23" and friday["tz"] == "America/New_York"
    assert datetime.fromtimestamp(friday["start"], tz=UTC).astimezone(NY).hour == 9
    assert datetime.fromtimestamp(friday["end"], tz=UTC).astimezone(NY).hour == 16
    assert session_bounds_for_date(datetime(2026, 10, 24).date()) is None  # Saturday
    assert session_bounds_for_date(datetime(2026, 10, 25).date()) is None  # Sunday
    early = session_bounds_for_date(datetime(2026, 11, 27).date())  # published early close
    assert datetime.fromtimestamp(early["end"], tz=UTC).astimezone(NY).hour == 13
