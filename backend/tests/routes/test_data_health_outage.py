"""A provider outage must be REPORTABLE.

`/api/data/health` crashed with HTTP 500 the moment any provider had never
succeeded. The alert dict carried:

    {"provider": "databento", "alert_type": "provider_down",
     "seconds_since_success": inf, "threshold_seconds": 120.0,
     "severity": "critical"}

`inf` is not JSON compliant, so `json.dumps(..., allow_nan=False)` raised
ValueError during response serialization. The route's own `except Exception`
could not catch it: serialization happens AFTER the handler returns, outside
the try block.

The result was the worst possible failure mode for a health endpoint -- it went
dark precisely when a provider was down and there was something to report. A
clean 200 with an empty alert list is what you get when everything is fine; a
500 is what you got when it was not. The 200 was only reachable because no
provider had been recorded yet.

These tests drive the real route through a real client, so they reproduce the
serialization failure rather than asserting on the dict in isolation.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from services.meta_observability import provider_monitor

    # A fresh monitor per test: this is a global singleton and provider state
    # is what triggers the bug.
    saved = dict(provider_monitor._providers)
    saved_alerted = {k: set(v) for k, v in provider_monitor._alerted.items()}
    provider_monitor._providers.clear()
    provider_monitor._alerted.clear()
    try:
        import server as S

        # Deliberately NOT `with TestClient(...)`: entering the context manager
        # runs startup/shutdown, which re-creates the server's asyncio.Lock on a
        # different event loop and raises "bound to a different event loop" on
        # the second test. lifespan is irrelevant to response serialization.
        yield TestClient(S.app)
    finally:
        provider_monitor._providers.clear()
        provider_monitor._providers.update(saved)
        provider_monitor._alerted.clear()
        provider_monitor._alerted.update(saved_alerted)


def test_health_survives_a_provider_that_never_succeeded(client):
    """The exact live condition: a provider recorded a failure, never a success."""
    from services.meta_observability import provider_monitor

    provider_monitor.record("databento", success=False)

    r = client.get("/api/data/health")

    assert r.status_code == 200, f"health went dark during an outage: {r.text[:200]}"


def test_health_reports_the_outage_instead_of_crashing(client):
    """It must not merely survive -- it must still TELL you what is wrong."""
    from services.meta_observability import provider_monitor

    provider_monitor.record("databento", success=False)

    body = client.get("/api/data/health").json()

    alerts = body.get("active_alerts", [])
    assert alerts, "a failed provider produced no active alert"
    assert any(a.get("provider") == "databento" for a in alerts), alerts


def test_health_payload_is_strictly_json_compliant(client):
    """No NaN/Infinity may reach the wire.

    allow_nan=False is the encoder FastAPI uses; it is what raised in prod.
    """
    from services.meta_observability import provider_monitor

    provider_monitor.record("databento", success=False)

    body = client.get("/api/data/health").json()

    # Re-encoding the parsed body must not need any non-standard float.
    json.dumps(body, allow_nan=False)


def test_never_succeeded_is_absent_not_infinite(client):
    """`inf` is the wrong value for "no success has happened yet".

    It is unrepresentable in JSON, and it also overstates what is known: the
    provider is not infinitely unhealthy, it simply has no success to measure
    from. The honest value is None (absent measurement), which serializes
    cleanly and says exactly what happened.
    """
    from services.meta_observability import provider_monitor

    provider_monitor.record("databento", success=False)

    alerts = client.get("/api/data/health").json().get("active_alerts", [])
    down = [a for a in alerts if a.get("alert_type") == "provider_down"]

    assert down, alerts
    for alert in down:
        value = alert.get("seconds_since_success")
        assert value != float("inf"), "inf cannot be JSON encoded"
        assert value is None, f"expected absent, got {value!r}"
