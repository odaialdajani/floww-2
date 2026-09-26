"""
backend/services/public_capability.py — Public 27-operation capability registry (T18).

Documented support ≠ account entitlement ≠ adapter implementation ≠ observed
behavior ≠ research eligibility. Each operation classified on all five axes.
F25–F27 reproduced by contract tests (mocked transport, no live calls).
"""

from __future__ import annotations

from typing import Any

#Saver: operation → {docs, wrapper, writes}
# Per-op classification axes (P11/R4-18, unknown-first):
#   tests: contract test status (mocked_only | none)
#   entitlement: commissioning_required (default) | verified
#   observed: not_observed (default) | mocked_only | observed
_OPERATIONS_BASE: list[dict[str, Any]] = [
    {"id": 1, "op": "create_token", "docs": "authorization/create-personal-access-token", "wrapper": "PublicBroker.auth", "writes": False},
    {"id": 2, "op": "get_accounts", "docs": "list-accounts/get-accounts", "wrapper": "PublicBroker.get_accounts", "writes": False},
    {"id": 3, "op": "get_portfolio_v2", "docs": "account-details/get-account-portfolio-v2", "wrapper": "PublicBroker.get_portfolio", "writes": False},
    {"id": 4, "op": "get_history", "docs": "account-details/get-history", "wrapper": "PublicBroker.get_history", "writes": False},
    {"id": 5, "op": "get_tax_lots", "docs": "tax-lot-selling/get-unrealized-tax-lots", "wrapper": "PublicBroker.get_unrealized_tax_lots", "writes": False},
    {"id": 6, "op": "get_tax_lots_symbol", "docs": "tax-lot-selling/get-unrealized-tax-lots-for-symbol", "wrapper": None, "writes": False},
    {"id": 7, "op": "get_tax_lots_csv", "docs": "tax-lot-selling/get-unrealized-tax-lots-csv", "wrapper": None, "writes": False},
    {"id": 8, "op": "get_all_instruments", "docs": "instrument-details/get-all-instruments", "wrapper": "PublicBroker.get_all_instruments", "writes": False},
    {"id": 9, "op": "get_instrument", "docs": "instrument-details/get-instrument", "wrapper": "PublicBroker.get_instrument", "writes": False},
    {"id": 10, "op": "search_bonds", "docs": "instrument-details/search-bonds", "wrapper": None, "writes": False},
    {"id": 11, "op": "get_quotes", "docs": "market-data/get-quotes", "wrapper": "PublicBroker.get_quotes", "writes": False},
    {"id": 12, "op": "get_bond_details", "docs": "market-data/get-bond-details", "wrapper": None, "writes": False},
    {"id": 13, "op": "get_option_expirations", "docs": "market-data/get-option-expirations", "wrapper": "PublicBroker.get_option_expirations", "writes": False},
    {"id": 14, "op": "get_option_chain", "docs": "market-data/get-option-chain", "wrapper": "PublicBroker.get_option_chain", "writes": False},
    {"id": 15, "op": "get_bars_v2", "docs": "market-data/get-bars-v2", "wrapper": "PublicBroker.get_bars", "writes": False},
    {"id": 16, "op": "get_bars_agg", "docs": "market-data/get-bars-v2-with-aggregation", "wrapper": "PublicBroker.get_bars", "writes": False},
    {"id": 17, "op": "preflight_single", "docs": "order-placement/preflight-single-leg", "wrapper": "PublicBroker.preflight_single_leg", "writes": False},
    {"id": 18, "op": "preflight_multi", "docs": "order-placement/preflight-multi-leg", "wrapper": "PublicBroker.preflight_multi_leg", "writes": False},
    {"id": 19, "op": "place_order", "docs": "order-placement/place-order", "wrapper": "PublicBroker.place_order (UNGATED LIVE — disarmed, no route)", "writes": True},
    {"id": 20, "op": "replace_order", "docs": "order-placement/replace-order", "wrapper": "PublicBroker.replace_order (disarmed)", "writes": True},
    {"id": 21, "op": "search_orders", "docs": "order-placement/search-orders", "wrapper": "PublicBroker.search_orders", "writes": False},
    {"id": 22, "op": "get_order_v2", "docs": "order-placement/get-order-v2", "wrapper": "PublicBroker.get_order_v2", "writes": False},
    {"id": 23, "op": "place_multileg", "docs": "order-placement/place-multileg-order", "wrapper": "PublicBroker.place_multileg_order (disarmed, type-fixed)", "writes": True},
    {"id": 24, "op": "get_order_legacy", "docs": "order-placement/get-order", "wrapper": "PublicBroker.get_order", "writes": False},
    {"id": 25, "op": "cancel_order", "docs": "order-placement/cancel-order", "wrapper": "PublicBroker.cancel_order (disarmed, DELETE-fixed)", "writes": True},
    {"id": 26, "op": "get_greeks", "docs": "option-details/get-option-greeks", "wrapper": "PublicBroker.get_option_greeks", "writes": False},
    {"id": 27, "op": "get_strategy_quote", "docs": "option-details/get-strategy-quote", "wrapper": "PublicBroker.get_strategy_quote", "writes": False},
]


def _classified(op: dict[str, Any]) -> dict[str, Any]:
    d = dict(op)
    d.setdefault("tests", "mocked_only" if d.get("wrapper") else "none")
    d.setdefault("entitlement", "commissioning_required")
    d.setdefault("observed", "not_observed")
    return d


OPERATIONS: list[dict[str, Any]] = [_classified(o) for o in _OPERATIONS_BASE]

UNAVAILABLE_IN_PUBLIC_ONLY = (
    "market-wide aggressor trade feed", "dealer inventory",
    "market-wide opening/closing flags", "guaranteed full expired-quote history",
    "general macro/earnings calendar feed",
)

# Source boundary for the 27-operation inventory: official Public docs
# navigation reviewed 23 Sep 2026 (S12–S27) + pinned SDK
# PublicDotCom/publicdotcom-py@00dca7d6e5ec7043311b8eb1d83144835dc80ee0.
# Documented capability ≠ commissioned account behavior (see COMMISSION.md).
DOCS_BASE = "https://public.com/api/docs"
REVIEWED_AT = "2026-09-23"


def registry() -> dict[str, Any]:
    return {"operations": OPERATIONS, "count": len(OPERATIONS),
            "docs_base": DOCS_BASE, "reviewed_at": REVIEWED_AT,
            "unavailable_in_public_only": list(UNAVAILABLE_IN_PUBLIC_ONLY),
            "entitlement": "per-account commissioning required; no live calls made here",
            "budget_baseline": "10 requests/second per account (changelog) with headroom; verify observed"}


def symbol_matrix(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """R7-06 per-symbol capability matrix from RECORDED observations only.

    Groups capability_observations rows by ticker: operations seen, last
    seen, usable totals. Entitlement is "unobserved" unless evidence says
    otherwise — a symbol with no observations is never "denied", and no
    other ticker's data ever substitutes (SPY cannot stand in for SPX).
    VEX inputs stay "unknown" until a chain with usable Greeks is observed.
    No live probing here: the matrix reports what was measured.
    """
    symbols: dict[str, Any] = {}
    for r in observations or []:
        t = str((r or {}).get("ticker") or "").upper()
        if not t:
            continue
        op = str((r or {}).get("operation") or "unknown")
        entry = symbols.setdefault(t, {"operations": {}, "last_seen": None,
                                       "entitlement": "unobserved",
                                       "vex_inputs": "unknown"})
        o = entry["operations"].setdefault(op, {"requested": 0, "returned": 0,
                                                "usable": 0, "last_at": None})
        for k in ("requested", "returned", "usable"):
            try:
                v = (r or {}).get(k)
                if v is not None:
                    o[k] += int(v)
            except (TypeError, ValueError):
                continue
        at = (r or {}).get("at") or (r or {}).get("at_ts")
        if at and (o["last_at"] is None or str(at) > str(o["last_at"])):
            o["last_at"] = at
        if entry["last_seen"] is None or (at and str(at) > str(entry["last_seen"])):
            entry["last_seen"] = at or entry["last_seen"]
        chain_ops = {"chain", "option_chain", "get_option_chain", "expiries",
                     "get_option_expirations"}
        if op in chain_ops and o["usable"] > 0:
            entry["vex_inputs"] = "derivable-if-iv"
    return {"symbols": symbols, "n_symbols": len(symbols),
            "note": "recorded observations only; unobserved symbols carry no claims"}
