"""B09 mapped-levels producer route — RED-first contract pins (2026-10-25).

Pins the executable b09_mapped_levels_contract in
C2-PRODUCER-CONTRACTS-20261024.json v2 (sha256 9f8f92ef...):
  * supported pairs only (C040 families); anything else refused unsupported-pair,
    rendered visibly (C043)
  * review-mode ratio = EXPLICIT HORIZONTAL LOCK: newest eligible ratio
    at-or-before the cursor, flat; known_at <= cursor; no-lookahead (C042)
  * zero denominator -> ratio-unavailable-at-cursor; futures pairs without a
    validated mapping -> unsupported-pair
  * only-overlap: no eligible shared-session pair -> unavailable no-shared-session
  * C115: the SPXW exposure-VWAP board-combine option stays REFUSED until an
    owner-reviewed combination spec exists
  * weekend cursor -> cursor-not-in-regular-session
Offline only: minimal router app + stubbed supplier seam + stubbed store
module (the established chart-suite pattern); zero network, zero account
action; no levels are invented.
"""
from __future__ import annotations

import sys
import types as pytypes
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

NY = ZoneInfo("America/New_York")


def _epoch(ny_date: str, hh: int, mm: int) -> float:
    d = datetime.fromisoformat(ny_date).replace(hour=hh, minute=mm, tzinfo=NY)
    return d.timestamp()


def _client(monkeypatch, by_ticker):
    stub = pytypes.ModuleType("services.duckdb_engine")
    stub.db = pytypes.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "services.duckdb_engine", stub)

    from routes import price_history

    async def supplier(ticker, period, aggregation, sessions, instrument_type="EQUITY"):
        bars = by_ticker.get(ticker, [])
        return list(bars), None, None

    monkeypatch.setattr(price_history, "_history_bars", supplier)
    app = FastAPI()
    app.include_router(price_history.router)
    return TestClient(app)


FRIDAY = "2026-10-23"
CURSOR = _epoch(FRIDAY, 12, 0)  # 12:00 ET, mid-session Friday
LEGEND_KEYS = ("diamond", "triangle")


def test_unsupported_pair_is_refused_visibly(monkeypatch):
    c = _client(monkeypatch, {"AAPL": [{"t": CURSOR - 60, "c": 230.0, "v": 1000}]})
    r = c.get(f"/api/heatseeker/mapped-levels/SPY?source=AAPL&cursor={CURSOR}")
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "refused"
    assert body["reason"] == "unsupported-pair"
    assert body["levels"] == []


def test_futures_pair_without_validated_mapping_is_refused(monkeypatch):
    c = _client(monkeypatch, {"ES": [{"t": CURSOR - 60, "c": 6000.0, "v": 10}]})
    r = c.get(f"/api/heatseeker/mapped-levels/SPY?source=ES&cursor={CURSOR}")
    assert r.json()["reason"] == "unsupported-pair"


def test_weekend_cursor_refused(monkeypatch):
    saturday = _epoch("2026-10-24", 12, 0)
    c = _client(monkeypatch, {"SPXW": [{"t": CURSOR - 60, "c": 6000.0, "v": 1}]})
    r = c.get(f"/api/heatseeker/mapped-levels/SPY?source=SPXW&cursor={saturday}")
    body = r.json()
    assert body["status"] == "refused"
    assert body["reason"] == "cursor-not-in-regular-session"


def test_zero_denominator_refused(monkeypatch):
    c = _client(monkeypatch, {
        "SPXW": [{"t": CURSOR - 120, "c": 6000.0, "v": 1}],
        "SPY": [{"t": CURSOR - 120, "c": 0.0, "v": 500}],
    })
    r = c.get(f"/api/heatseeker/mapped-levels/SPY?source=SPXW&cursor={CURSOR}")
    assert r.json()["reason"] == "ratio-unavailable-at-cursor"


def test_future_source_bars_excluded_no_shared_session(monkeypatch):
    # Source bars exist ONLY after the cursor: excluded; no eligible pair.
    c = _client(monkeypatch, {
        "SPXW": [{"t": CURSOR + 3600, "c": 6000.0, "v": 1}],
        "SPY": [{"t": CURSOR - 120, "c": 600.0, "v": 500}],
    })
    r = c.get(f"/api/heatseeker/mapped-levels/SPY?source=SPXW&cursor={CURSOR}")
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "no-shared-session"


def test_ratio_lock_is_newest_eligible_pair_before_cursor(monkeypatch):
    # Two eligible pairs; the LOCK must use the newest at-or-before cursor,
    # and a future pair (after-cursor) must NOT shift the lock.
    c = _client(monkeypatch, {
        "SPXW": [{"t": CURSOR - 600, "c": 5900.0, "v": 1},
                 {"t": CURSOR - 300, "c": 6000.0, "v": 1},
                 {"t": CURSOR + 300, "c": 6500.0, "v": 1}],
        "SPY": [{"t": CURSOR - 600, "c": 590.0, "v": 50},
                {"t": CURSOR - 300, "c": 600.0, "v": 50},
                {"t": CURSOR + 300, "c": 650.0, "v": 50}],
    })
    r = c.get(f"/api/heatseeker/mapped-levels/SPY?source=SPXW&cursor={CURSOR}")
    body = r.json()
    assert body["status"] == "available"
    ratio = body["ratio"]
    assert ratio["value"] == pytest.approx(6000.0 / 600.0)
    assert ratio["provenance"]["known_at"] <= CURSOR
    # the future pair is NOT the provenance anchor
    assert ratio["provenance"]["window"]["end"] <= CURSOR


def test_available_body_carries_provenance_and_shape_legend(monkeypatch):
    c = _client(monkeypatch, {
        "SPXW": [{"t": CURSOR - 300, "c": 6000.0, "v": 1}],
        "SPY": [{"t": CURSOR - 300, "c": 600.0, "v": 50}],
    })
    r = c.get(f"/api/heatseeker/mapped-levels/SPY?source=SPXW&cursor={CURSOR}")
    body = r.json()
    assert body["status"] == "available"
    assert body["source"] == "SPXW" and body["target"] == "SPY"
    prov = body["ratio"]["provenance"]
    for key in ("source_bars_used", "target_bars_used", "window", "known_at"):
        assert key in prov
    assert prov["source_bars_used"] == 1 and prov["target_bars_used"] == 1
    legend = body["legend"]
    assert sorted(legend.keys()) == sorted(LEGEND_KEYS)
    assert all(isinstance(legend[k], str) and legend[k] for k in LEGEND_KEYS)
    assert isinstance(body["levels"], list)
    assert body["levels_status"]


def test_spxw_board_combination_gate_is_a_refusal(monkeypatch):
    c = _client(monkeypatch, {
        "SPXW": [{"t": CURSOR - 300, "c": 6000.0, "v": 1}],
        "SPY": [{"t": CURSOR - 300, "c": 600.0, "v": 50}],
    })
    r = c.get(f"/api/heatseeker/mapped-levels/SPY?source=SPXW&cursor={CURSOR}"
              "&combine=exposure_vwap")
    body = r.json()
    assert body["status"] == "refused"
    assert body["reason"] == "spxw-board-combination-unavailable"


def test_ndx_family_supported(monkeypatch):
    c = _client(monkeypatch, {
        "NDX": [{"t": CURSOR - 300, "c": 24000.0, "v": 1}],
        "QQQ": [{"t": CURSOR - 300, "c": 600.0, "v": 50}],
    })
    r = c.get(f"/api/heatseeker/mapped-levels/QQQ?source=NDX&cursor={CURSOR}")
    body = r.json()
    assert body["status"] == "available"
    assert body["ratio"]["value"] == pytest.approx(24000.0 / 600.0)
