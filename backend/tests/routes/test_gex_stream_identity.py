"""EXPOSURE-02: the GEX stream must carry its own reading identity.

The Stock chart renders the REST snapshot and the websocket stream side by
side. The stream payload historically carried total_gex/king/regime with no
formula, version, units, expiry scope, or coverage — so a snapshot reading
(NEGATIVE / king 767) and a stream reading (positive / king 790) present as
one contradictory signal instead of two separately-scoped readings.

This test drives the real websocket_gex handler with a stub socket and
deterministic computation fakes, then pins both halves of the contract:
the exposure math is unchanged AND the identity fields are present.
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, patch

import pytest

import server
from server import websocket_gex


class _Stop(Exception):
    """Raised by the stub socket to end the handler's loop after one payload."""


class _Socket:
    def __init__(self):
        self.sent = []

    async def accept(self):
        return None

    async def send_json(self, data):
        self.sent.append(data)
        raise _Stop("captured one payload")

    async def close(self, code=1000, reason=""):
        return None


_STRIKES = [
    {"strike": 767.0, "gex": -1300000000.0},
    {"strike": 790.0, "gex": 668900000.0},
]
_NODES = {"king": {"strike": 767.0, "gex": -1300000000.0}, "regime": "negative"}
_RAW = {
    "spot": 775.0,
    "contracts": [
        {"strike": 767, "expiry": "2026-10-09"},
        {"strike": 790, "expiry": "2026-10-09"},
        {"strike": 800, "expiry": "2026-10-10"},
    ],
    "expiries": ["2026-10-09", "2026-10-10"],
    "event_time": "2026-10-09T00:46:17+00:00",
}
_OBSERVATION = {
    "event_time": "2026-10-09T00:46:17+00:00",
    "source": "public_api",
    "status": "ok",
    "received_at": "2026-10-09T00:46:20+00:00",
}


def _payload():
    ws = _Socket()
    with (
        patch("server.verify_ws_token", AsyncMock(return_value=True), create=True),
        patch.object(
            server,
            "fetch_spot_and_chains_merged",
            AsyncMock(return_value=_RAW),
            create=True,
        ),
        patch.object(server, "compute_gex_by_strike", return_value=_STRIKES),
        patch.object(server, "classify_nodes", return_value=_NODES),
        patch(
            "services.market_provenance.spot_provenance",
            return_value=_OBSERVATION,
        ),
        patch("asyncio.sleep", AsyncMock()),
    ):
        with contextlib.suppress(_Stop):
            asyncio.run(websocket_gex(ws, "SPY"))
    readings = [p for p in ws.sent if isinstance(p, dict) and "total_gex" in p]
    assert readings, f"expected one stream reading, got: {ws.sent!r}"
    return readings[0]


def test_empty_chain_builds_honest_reading():
    """No strikes and no scope metadata must not crash or fabricate."""
    from unittest.mock import patch

    with patch(
        "services.market_provenance.spot_provenance",
        return_value={
            "event_time": None,
            "source": "unknown",
            "status": "unavailable",
            "received_at": None,
        },
    ):
        payload = server.build_gex_stream_payload(
            "SPY", 0.0, [], {"king": None, "regime": None}, {},
            "2026-10-09T00:00:00+00:00",
        )
    assert payload["total_gex"] == 0.0
    assert payload["n_strikes"] == 0
    assert payload["n_contracts"] == 0
    assert payload["expiries"] == []
    assert payload["king"] is None
    assert payload["regime"] is None
    assert payload["formula_version"] == "gex.v2"


def test_null_nodes_builds_honest_reading():
    """A missing node map must not crash the socket loop."""
    from unittest.mock import patch

    with patch(
        "services.market_provenance.spot_provenance",
        return_value={
            "event_time": None,
            "source": "unknown",
            "status": "unavailable",
            "received_at": None,
        },
    ):
        payload = server.build_gex_stream_payload(
            "SPY", 100.0, [{"strike": 100.0, "gex": 10.0}], None, {},
            "2026-10-09T00:00:00+00:00",
        )
    assert payload["total_gex"] == 10.0
    assert payload["king"] is None
    assert payload["regime"] is None


def test_stream_math_is_unchanged():
    """The identity fix must not move the exposure numbers."""
    payload = _payload()
    assert payload["total_gex"] == round(sum(s["gex"] for s in _STRIKES), 0)
    assert payload["king"] == _NODES["king"]
    assert payload["regime"] == _NODES["regime"]
    assert payload["spot"] == _RAW["spot"]


def test_stream_carries_reading_identity():
    """Formula, version, units, expiry scope and coverage ride with the reading."""
    payload = _payload()
    assert payload["formula_version"] == "gex.v2"
    assert payload["series_version"] == "gex-stream.ws.v1"
    assert payload["reading"] == "stream"
    assert payload["units"] == "USD"
    assert payload["expiries_requested"] == 4
    assert payload["expiries"] == _RAW["expiries"]
    assert payload["n_contracts"] == len(_RAW["contracts"])
    assert payload["n_strikes"] == len(_STRIKES)
