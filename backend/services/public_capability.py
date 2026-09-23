"""
backend/services/public_capability.py — Public 27-operation capability registry (T18).

Documented support ≠ account entitlement ≠ adapter implementation ≠ observed
behavior ≠ research eligibility. Each operation classified on all five axes.
F25–F27 reproduced by contract tests (mocked transport, no live calls).
"""

from __future__ import annotations

from typing import Any

#Saver: operation → {docs, wrapper, writes}
OPERATIONS: list[dict[str, Any]] = [
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

UNAVAILABLE_IN_PUBLIC_ONLY = (
    "market-wide aggressor trade feed", "dealer inventory",
    "market-wide opening/closing flags", "guaranteed full expired-quote history",
    "general macro/earnings calendar feed",
)


def registry() -> dict[str, Any]:
    return {"operations": OPERATIONS, "count": len(OPERATIONS),
            "unavailable_in_public_only": list(UNAVAILABLE_IN_PUBLIC_ONLY),
            "entitlement": "per-account commissioning required; no live calls made here",
            "budget_baseline": "10 requests/second per account (changelog) with headroom; verify observed"}
