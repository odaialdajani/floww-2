"""S06 server-owned preflight validity: frozen caller-clock probe.

A caller that freezes ctx["now"] must not keep a stale broker verdict
fresh past the TTL: the server wall-clock bound refuses it and forces a
re-fetch. Fake broker only; no live calls.
"""
import sys

sys.path.insert(0, "backend")

from datetime import UTC, datetime


def _intent(**kw):
    intent = {
        "intent_version": "execution-intent.v1",
        "observation_id": "obs_s6",
        "replay_id": None,
        "ticker": "SPY",
        "contract": {
            "osi": "SPY260904C00760000",
            "expiry": "2026-09-04",
            "option_type": "CALL",
            "strike_exact": "760.00",
            "multiplier": "100",
            "multiplier_provenance": "vendor-instrument",
        },
        "side": "BUY",
        "open_close": "OPEN",
        "quantity": 1,
        "limit_price": "3.15",
        "tick": "0.05",
        "account_id": "ACCT-1",
        "venue": "PUBLIC",
        "cash_margin_choice": "CASH",
        "budget": {"preflight_total": "318.20", "fees": "3.20",
                   "asof": "2026-10-02T15:00:00+00:00"},
        "session_policy": {"session": "regular", "freshness_s": 30,
                           "confirmation": "quoted"},
        "risk_policy_version": "research_barriers.v1",
        "execution_owner": "FLOWW_BACKEND",
        "entry_pause_ack": False,
        "replay_authorization": None,
    }
    intent.update(kw)
    return intent


def _ctx(**kw):
    base = {
        "quotes": {"bid": "3.10", "ask": "3.20",
                   "bid_ts": "2026-10-02T14:59:40+00:00",
                   "ask_ts": "2026-10-02T14:59:41+00:00"},
        "now": datetime(2026, 10, 2, 15, 0, tzinfo=UTC),
        "account": {"options_level": "2", "entitlement": "verified",
                    "margin": True},
        "snapshot_id": "snap_1",
        "supported_expiries": ["2026-09-04"],
        "supported_products": ["OPTION", "EQUITY"],
    }
    base.update(kw)
    return base


class _VerdictBroker:
    def __init__(self):
        self.calls = 0

    async def preflight_single_leg(self, **kw):
        self.calls += 1
        return {"total": "318.20", "fees": "3.20", "buying_power_ok": True}


def test_frozen_caller_clock_cannot_extend_freshness(monkeypatch):
    import asyncio

    import services.public_execution_lifecycle as lc

    lc._reset_for_tests()
    intent, ctx = _intent(), _ctx()
    broker = _VerdictBroker()
    assert asyncio.run(lc.preflight(intent, ctx, broker))["cached"] is False
    assert lc.preflight_gate(intent, ctx) is None
    # Wall time advances 120s while the caller clock stays frozen: the
    # cached verdict is stale and the gate refuses it.
    real_wall = lc._wall_now()
    monkeypatch.setattr(lc, "_wall_now", lambda: real_wall + 120.0)
    assert lc.preflight_gate(intent, ctx) == "STALE_PREFLIGHT"
    assert lc.has_fresh_preflight(intent, ctx) is False
    # A re-fetch happens (no free pass on the stale cache) and the fresh
    # verdict satisfies the gate again at the advanced wall time.
    assert asyncio.run(lc.preflight(intent, ctx, broker))["cached"] is False
    assert broker.calls == 2
    assert lc.preflight_gate(intent, ctx) is None
    lc._reset_for_tests()


def test_actual_wrapper_preserves_option_identity_and_cash_choice():
    import asyncio
    import json

    import httpx

    import services.public_execution_lifecycle as lc
    from services.public_api import BASE_URL, PublicBroker

    seen = []
    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"buying_power_ok": True})

    async def run():
        client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(respond))
        broker = PublicBroker(secret_key="offline-only", client=client)
        broker._access_token, broker._token_expires_at = "offline", float("inf")
        lc._reset_for_tests()
        try:
            result = await lc.preflight(_intent(open_close="CLOSE"), _ctx(), broker)
            assert result["ok"] is True
        finally:
            await broker.close()
            lc._reset_for_tests()

    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0]["instrument"] == {"symbol": "SPY260904C00760000", "type": "OPTION"}
    assert seen[0]["openCloseIndicator"] == "CLOSE"
    assert seen[0]["useMargin"] is False
