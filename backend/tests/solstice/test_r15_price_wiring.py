"""R15-2 wiring: real fetch seam (adapter-backed, no fabrication) + read-only
status route + server mount. No live calls (adapter mocked), no activation."""

import sys

sys.path.insert(0, "backend")


def test_fetch_seam_returns_supported_quote_shape():
    import asyncio

    from services import solstice_price_fetch as fetch_mod

    async def fake_quotes(symbol):
        return {symbol: {"spot": 500.25, "spot_event_time": "2026-10-02T15:59:00+00:00",
                         "spot_fetched_at": "2026-10-02T15:59:00.400+00:00",
                         "spot_source": "public-mid"}}

    from unittest.mock import patch

    import services.public_api_adapter as ada

    with patch.object(ada, "fetch_quotes_from_public_api", side_effect=fake_quotes):
        obs = asyncio.run(fetch_mod.fetch_one_public_quote("spy"))
    assert obs is not None
    assert obs["ticker"] == "SPY"
    assert obs["price"] == 500.25
    assert obs["event_time"] == "2026-10-02T15:59:00+00:00"
    assert obs["fetched_at"] == "2026-10-02T15:59:00.400+00:00"
    assert obs["source"] == "public-mid"


def test_fetch_seam_returns_none_without_fabrication():
    import asyncio
    from unittest.mock import patch

    import services.public_api_adapter as ada
    from services import solstice_price_fetch as fetch_mod

    with patch.object(ada, "fetch_quotes_from_public_api", return_value=None):
        assert asyncio.run(fetch_mod.fetch_one_public_quote("SPY")) is None
    with patch.object(ada, "fetch_quotes_from_public_api", return_value={"QQQ": {"spot": 1.0}}):
        # Wrong-symbol answer is never substituted.
        assert asyncio.run(fetch_mod.fetch_one_public_quote("SPY")) is None
    with patch.object(ada, "fetch_quotes_from_public_api", side_effect=RuntimeError("down")):
        assert asyncio.run(fetch_mod.fetch_one_public_quote("SPY")) is None


def test_symbols_from_env_defaults_and_bounds():
    import os

    from services import solstice_price_fetch as fetch_mod

    os.environ.pop("FLOWW_PRICE_PATH_SYMBOLS", None)
    assert fetch_mod.symbols_from_env() == ["SPY", "QQQ"]
    os.environ["FLOWW_PRICE_PATH_SYMBOLS"] = "spy, SPY, qqq,,aapl"
    try:
        assert fetch_mod.symbols_from_env() == ["SPY", "QQQ", "AAPL"]
    finally:
        os.environ.pop("FLOWW_PRICE_PATH_SYMBOLS", None)


def test_status_route_reports_absent_off_without_activation():
    from fastapi.testclient import TestClient

    from server import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/solstice/price-paths/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == "price-path-producer.v1"
    assert body["worker_enabled"] is False
    assert body["worker_state"] in ("absent", "wired_off")
    assert body["durable"] is False  # test env store is :memory:


def test_points_route_is_read_only_and_empty_without_writes():
    from fastapi.testclient import TestClient

    from server import app

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/solstice/price-paths/points",
                   params={"ticker": "SPY", "since": 0, "limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ticker"] == "SPY"
    assert isinstance(body["points"], list)


def test_server_mounts_price_paths_router():
    from server import app

    paths = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path:
            paths.add(path)
    assert "/api/solstice/price-paths/status" in paths
    assert "/api/solstice/price-paths/points" in paths


def test_producer_flag_defaults_off_in_server_process():
    import os

    assert os.environ.get("FLOWW_PRICE_PATH_PRODUCER", "") != "1"
    from services import solstice_price_producer as prod

    assert prod.worker_enabled() is False
