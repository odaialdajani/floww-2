from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from server import app


def test_listing_only_never_fetches_chains_and_preserves_window_verdicts():
    today = datetime.now(ZoneInfo("America/New_York")).date()
    dates = [(today + timedelta(days=n)).isoformat() for n in (0, 1, 4, 8)]
    with patch("services.public_api_adapter.fetch_option_expiry_listing",
               new=AsyncMock(return_value={"expiries": dates, "listing_capped": False})) as listing, \
         patch("services.public_api_adapter.fetch_chain_from_public_api",
               new=AsyncMock(side_effect=AssertionError("no chains for listing"))):
        response = TestClient(app).get(
            "/api/solstice/price-paths/expiries?ticker=SPY&min_dte=0&max_dte=7&expirations=1&listing_only=true")
    assert response.status_code == 200
    body = response.json()
    listing.assert_awaited_once_with("SPY")
    assert body["version"] == "coverage-read.v1"
    assert [r["dte"] for r in body["expiries"] if r["admitted"]] == [0, 1, 4]
    assert body["coverage"]["listing_capped"] is False
    assert body["range_map"]["complete"] is True


def test_listing_only_rejects_date_prefixes_and_marks_coverage_incomplete():
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    with patch("services.public_api_adapter.fetch_option_expiry_listing",
               new=AsyncMock(return_value={"expiries": [today + "garbage"], "listing_capped": False})):
        response = TestClient(app).get(
            "/api/solstice/price-paths/expiries?ticker=SPY&min_dte=0&max_dte=7&listing_only=true")
    body = response.json()
    assert body["n_admitted"] == 0
    assert body["expiries"][0]["reason"] == "UNPARSEABLE_EXPIRY"
    assert body["range_map"]["complete"] is False
