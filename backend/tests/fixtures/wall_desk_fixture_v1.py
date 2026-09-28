"""Frozen C5 evidence fixture: source-shaped Public input and expected packet.

This is a redacted, hand-checkable desk packet for OpenCode/Hermes
coordination. It is not generated from a live vendor feed and carries no
credentials, accounts, or tool authority.

Coordinate system
-----------------
One underlying price (S=100), one strike coordinate (K=100), two expiries.
Opposing call/put contracts share the strike so gross/net cancellation is
visible. One contract has missing delta. One quote is stale. Two
chronological observations are supplied for history/replay checks.

Known expectations (S=100, multiplier=100, 1% move factor=0.01)
--------------------------------------------------------------
u = gamma*m*S^2*0.01 = 0.01*100*10000*0.01 = 100 USD/1% per contract unit.

Observation T0, expiry E1:
- call: gamma .01, OI 10, |delta| .5 -> raw +1000, delta-weighted +500
- put:  gamma .01, OI 10, |delta| .5 -> raw -1000, delta-weighted -500
- expiry E1 totals: raw gross 2000, raw net 0, delta gross 1000, delta net 0
- missing-delta call: gamma .01, OI 10, delta None -> raw +1000, delta N/A
- volume gamma uses session volume, not OI:
  call V=5 -> +500; put V=2 -> -200; totals gross-like 700, net +300.

Units: USD per 1% spot move. Formula version: gex.v2.
"""

from __future__ import annotations

FIXTURE_VERSION = "wall-desk-fixture.v1"
FORMULA_VERSION = "gex.v2"
SPOT = 100.0

SOURCE_OBSERVATION_T0 = {
    "ticker": "SPY",
    "spot": SPOT,
    "asof": "2030-01-02T14:00:00+00:00",
    "source_received_at": "2030-01-02T14:00:01+00:00",
    "data_source": "development_fixture",
    "expiries": ["2030-01-15", "2030-02-19"],
    "contracts": [
        {
            "osi": "CALL-E1",
            "type": "call",
            "strike": 100,
            "expiry": "2030-01-15",
            "multiplier": 100,
            "oi": 10,
            "volume": 5,
            "gamma": 0.01,
            "delta": 0.5,
            "quote_status": "current",
        },
        {
            "osi": "PUT-E1",
            "type": "put",
            "strike": 100,
            "expiry": "2030-01-15",
            "multiplier": 100,
            "oi": 10,
            "volume": 2,
            "gamma": 0.01,
            "delta": -0.5,
            "quote_status": "current",
        },
        {
            "osi": "CALL-E1-NODELTA",
            "type": "call",
            "strike": 100,
            "expiry": "2030-01-15",
            "multiplier": 100,
            "oi": 10,
            "volume": 1,
            "gamma": 0.01,
            "delta": None,
            "quote_status": "current",
        },
        {
            "osi": "CALL-E2-STALE",
            "type": "call",
            "strike": 100,
            "expiry": "2030-02-19",
            "multiplier": 100,
            "oi": 4,
            "volume": 0,
            "gamma": 0.01,
            "delta": 0.25,
            "quote_status": "stale",
        },
    ],
}

SOURCE_OBSERVATION_T1 = {
    "ticker": "SPY",
    "spot": SPOT,
    "asof": "2030-01-02T14:01:00+00:00",
    "source_received_at": "2030-01-02T14:01:01+00:00",
    "data_source": "development_fixture",
    "expiries": ["2030-01-15", "2030-02-19"],
    "contracts": [
        {
            "osi": "CALL-E1",
            "type": "call",
            "strike": 100,
            "expiry": "2030-01-15",
            "multiplier": 100,
            "oi": 10,
            "volume": 7,
            "gamma": 0.01,
            "delta": 0.5,
            "quote_status": "current",
        },
        {
            "osi": "PUT-E1",
            "type": "put",
            "strike": 100,
            "expiry": "2030-01-15",
            "multiplier": 100,
            "oi": 10,
            "volume": 2,
            "gamma": 0.01,
            "delta": -0.5,
            "quote_status": "current",
        },
    ],
}

EXPECTED_PACKET_T0 = {
    "fixture_version": FIXTURE_VERSION,
    "formula_version": FORMULA_VERSION,
    "snapshot_id": "fixture-t0",
    "wall_id": "K100",
    "units": "USD/1% move",
    "raw_gross": 3400.0,
    "raw_net": 1400.0,
    "delta_gross": 1100.0,
    "delta_net": 100.0,
    "delta_missing": 1,
    "volume_gross_like": 800.0,
    "volume_net": 400.0,
    "coverage": {
        "expiries": ["2030-01-15", "2030-02-19"],
        "stale": ["CALL-E2-STALE"],
        "missing_delta": ["CALL-E1-NODELTA"],
    },
    "reason_codes": ["DELTA_MISSING", "QUOTE_STALE"],
}

EXPECTED_WINDOW_T0_T1 = {
    "call_delta_volume": 2.0,
    "put_delta_volume": 0.0,
    "window_gross_like": 100.0,
    "window_net": 100.0,
    "interval": {
        "start": SOURCE_OBSERVATION_T0["asof"],
        "end": SOURCE_OBSERVATION_T1["asof"],
    },
}
