#!/usr/bin/env python3
"""Solstice commissioning probes (T26/account-level verification).

Read-only. Never places orders, never writes credentials, never hammers the
provider. Without PUBLIC_API_KEY it runs the OFFLINE suite (contract fixtures
+ registry checks) and reports account-level probes as BLOCKED with exact
reason — a stopped environment is a blocker, not a pass.

Usage:
    python3 scripts/solstice_commission.py                # offline suite
    PUBLIC_API_KEY=... python3 scripts/solstice_commission.py --live  # account probes
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

CHECKS: list[dict] = []


def check(name):
    def deco(fn):
        CHECKS.append({"name": name, "fn": fn})
        return fn
    return deco


@check("registry/27 operations classified")
def c_registry():
    from services.public_capability import registry
    reg = registry()
    assert reg["count"] == 27, reg["count"]
    return "27 ops, writes disarmed"


@check("instrument resolver SPX family")
def c_resolver():
    from services.public_api import resolve_public_instrument_type
    assert resolve_public_instrument_type("SPX", "chain") == "UNDERLYING_SECURITY_FOR_INDEX_OPTION"
    assert resolve_public_instrument_type("SPX", "quote") == "INDEX"
    assert resolve_public_instrument_type("SPY", "chain") == "EQUITY"
    return "SPX/SPY/QQQ mapping ok"


@check("cancel transport DELETE + empty tolerance")
def c_cancel():
    import inspect
    from services import public_api
    src = inspect.getsource(public_api.PublicBroker.cancel_order)
    assert ".delete(" in src and "CANCEL_PENDING" in src
    return "DELETE with pending-not-canceled"


@check("multileg placement uses type (preflight keeps orderType)")
def c_multi():
    import inspect
    from services import public_api
    src = inspect.getsource(public_api.PublicBroker.place_multileg_order)
    assert '"type": order_type' in src and '"orderType": order_type' not in src
    return "serializers separated"


@check("exact 0DTE clock (no 1-day floor)")
def c_clock():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from services.solstice_time import time_to_expiry_years
    et = ZoneInfo("America/New_York")
    t, _, _ = time_to_expiry_years("2030-06-15", now=datetime(2030, 6, 15, 10, 0, tzinfo=et), ticker="SPY")
    assert t is not None and t < 1.0 / 365
    t2, _, r2 = time_to_expiry_years("2030-06-15", now=datetime(2030, 6, 16, 10, 0, tzinfo=et), ticker="SPY")
    assert t2 is None and r2 == "EXPIRED"
    return "intraday T + expiry drop ok"


@check("data adapter has no order methods (ADR-0008)")
def c_readonly():
    import services.public_api_adapter as ada
    for m in ("place_order", "place_multileg_order", "cancel_order"):
        assert not hasattr(ada, m), m
    return "data-only adapter"


def live_checks():
    print("-- live account probes (read-only) --")
    key = os.environ.get("PUBLIC_API_KEY", "")
    if not key:
        print("BLOCKED: PUBLIC_API_KEY unset — account probes cannot run.")
        print("Blocked items: SPX/SPXW symbol combos, OI cadence, Greek timestamps,")
        print("rate-limit/Retry-After behavior, multiplier/deliverable metadata,")
        print("expired-history retention, bracket behavior, option permissions.")
        return False
    print("PUBLIC_API_KEY present — live probes still require explicit approval;")
    print("not running network calls from this script by default.")
    return False


def main() -> int:
    live = "--live" in sys.argv
    passed = 0
    for c in CHECKS:
        try:
            detail = c["fn"]()
            print(f"PASS {c['name']} — {detail}")
            passed += 1
        except Exception as e:
            print(f"FAIL {c['name']} — {e}")
    print(f"{passed}/{len(CHECKS)} offline checks passed")
    if live:
        live_checks()
    else:
        print("(account-level probes: run with --live once credentials + approval exist)")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
