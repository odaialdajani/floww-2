"""
In-process tests for the legacy Heatseeker API surface (root / tickers /
glossary / history / etc.).

Migrated from the requests-against-localhost driver to FastAPI's TestClient
so the suite runs in CI without a backend on :8000. Heavy heatmap / movers /
trinity tests are kept here (skipped) so the original intent is preserved
and a developer can flip them on for a manual smoke run.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make ``server`` importable when pytest is invoked from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app  # noqa: E402


def _has_nan_or_inf(obj):
    if isinstance(obj, float):
        return math.isnan(obj) or math.isinf(obj)
    if isinstance(obj, dict):
        return any(_has_nan_or_inf(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_nan_or_inf(v) for v in obj)
    return False


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# --------- Root + tickers ---------

def test_root(client):
    r = client.get("/api/")
    assert r.status_code == 200
    d = r.json()
    assert d.get("app") == "confluence-decoder"
    assert "version" in d and "ts" in d


def test_tickers_list(client):
    r = client.get("/api/tickers")
    assert r.status_code == 200
    d = r.json()
    assert "trinity" in d and "default" in d and "popular" in d
    assert d["trinity"] == ["^SPX", "SPY", "QQQ"]
    assert "SPY" in d["default"] and "QQQ" in d["default"]
    assert isinstance(d["popular"], list) and len(d["popular"]) > 10


# --------- Glossary (static) ---------

def test_glossary(client):
    r = client.get("/api/patterns/glossary")
    assert r.status_code == 200
    d = r.json()
    for k in ("Rug", "Reverse Rug", "Pika Cloud", "Beach Ball", "Whipsaw",
              "Rainbow Road", "King Node", "Floor", "Ceiling", "Gatekeeper",
              "Air Pocket"):
        assert k in d, f"missing glossary entry {k}"


# --------- History (depends on Mongo cursor; mock the snapshots collection) ---

def test_history_spy(client):
    """
    /history/{ticker} streams snapshots from Mongo. Replace ``db.snapshots``
    with a stub whose ``find`` returns an async cursor over a single doc.
    """
    from unittest.mock import patch

    import server as srv

    class _AsyncCursor:
        def __init__(self, rows):
            self._rows = list(rows)

        def sort(self, *_, **__):
            return self

        def limit(self, _n):
            return self

        def __aiter__(self):
            self._it = iter(self._rows)
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration

        async def to_list(self, length=None):
            return self._rows[:length] if length else list(self._rows)

    class _Snapshots:
        def find(self, *_, **__):
            return _AsyncCursor([{"ticker": "SPY", "ts": "2026-05-18T00:00:00Z"}])

    class _DB:
        snapshots = _Snapshots()

    with patch.object(srv, "db", _DB()):
        r = client.get("/api/history/SPY")

    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "SPY"
    assert isinstance(d["snapshots"], list)


# --------- Heavy chain-dependent endpoints — integration only ---------
#
# /heatmap, /trinity, /movers all chain together yfinance + Polygon + Mongo
# writes inside the route. The single chain mock isn't enough; they remain
# skipped here and live in the QA smoke suite that runs against a real
# backend. TODO: trim build_heatmap so its tap_counts / Mongo writes can be
# stubbed in unit tests too.

@pytest.mark.skip(reason="build_heatmap reaches yfinance/Polygon/Mongo; integration only")
def test_heatmap_spy(client):
    r = client.get("/api/heatmap/SPY?expiries=2")
    assert r.status_code == 200, r.text
    d = r.json()
    raw = r.content.decode()
    assert "NaN" not in raw and "Infinity" not in raw
    assert d["ticker"] == "SPY"
    assert isinstance(d["spot"], (int, float)) and d["spot"] > 0
    assert isinstance(d["strikes"], list) and len(d["strikes"]) > 0
    for s in d["strikes"]:
        for k in ("strike", "gex", "call_gex", "put_gex", "lifecycle",
                  "tap_prob", "taps"):
            assert k in s, f"missing {k}"
    nodes = d["nodes"]
    for k in ("king", "floors", "ceilings", "gatekeepers", "air_pockets",
              "regime"):
        assert k in nodes
    assert nodes["king"] and "strike" in nodes["king"]
    assert isinstance(d["patterns"], list)
    assert isinstance(d["velocity"], dict)
    assert "velocity_score" in d["velocity"]
    assert "tap_counts" in d
    assert "asof" in d
    assert not _has_nan_or_inf(d)


@pytest.mark.skip(reason="build_heatmap reaches yfinance/Polygon/Mongo; integration only")
def test_heatmap_qqq(client):
    r = client.get("/api/heatmap/QQQ?expiries=2")
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "QQQ"
    assert d["spot"] > 0
    assert len(d["strikes"]) > 0
    assert not _has_nan_or_inf(d)


@pytest.mark.skip(reason="build_heatmap reaches yfinance/Polygon/Mongo; integration only")
def test_heatmap_spx(client):
    r = client.get("/api/heatmap/%5ESPX?expiries=2")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "^SPX"
    assert d["spot"] > 0
    assert len(d["strikes"]) > 0


@pytest.mark.skip(reason="trinity fans out to build_heatmap × 3; integration only")
def test_trinity(client):
    r = client.get("/api/trinity")
    assert r.status_code == 200
    d = r.json()
    assert "tickers" in d and "alignment" in d
    for t in ("^SPX", "SPY", "QQQ"):
        assert t in d["tickers"]
    align = d["alignment"]
    assert align["verdict"] in ("full_alignment", "partial_alignment", "divergence")
    assert "confluence" in align and "regime" in align


@pytest.mark.skip(reason="hits Polygon for top movers; integration only")
def test_movers(client):
    r = client.get("/api/movers?limit=5")
    assert r.status_code == 200
    d = r.json()
    assert "results" in d
    assert isinstance(d["results"], list)
    if d["results"]:
        row = d["results"][0]
        for k in ("ticker", "pct", "close"):
            assert k in row
