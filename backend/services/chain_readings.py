"""Shared option-table readings; missing inputs never become a measured zero."""
import math
from contextlib import suppress

from bs_greeks import bs_charm, bs_vanna, dollar_gex_per_contract
from domain.exposure_metrics import option_type_sign
from services.gex_core import DIV_YIELD


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def chain_readings(contracts, spot, ticker):
    spot = finite(spot)
    rows = []
    for contract in contracts:
        sign = option_type_sign(contract.get('type'))
        if sign is None:
            continue
        row = dict(contract)
        for key in ('strike','iv','delta','gamma','vega','theta','volume','bid','ask','T'):
            row[key] = finite(contract.get(key))
        oi = row['oi'] = finite(contract.get('oi', contract.get('open_interest')))
        gamma, strike, iv, years = (row[k] for k in ('gamma','strike','iv','T'))
        row.update(gex=None, vanna=finite(contract.get("vanna")), charm=finite(contract.get("charm")), moneyness_pct=None, dte=None)
        if years is not None and years >= 0:
            row['dte'] = int(round(years * 365))
        if spot is not None and spot > 0:
            if gamma is not None and gamma >= 0 and oi is not None and oi >= 0:
                row['gex'] = finite(sign * dollar_gex_per_contract(gamma, oi, spot))
            if strike is not None and strike > 0:
                row['moneyness_pct'] = finite((spot-strike)/spot*100)
                if iv is not None and iv > 0 and years is not None and years > 0:
                    q = DIV_YIELD.get(ticker, 0.0)
                    for key, fn, extra in (('vanna',bs_vanna,{}),('charm',bs_charm,{'kind': row['type']})):
                        if row[key] is not None:
                            continue
                        with suppress(ValueError, OverflowError, ZeroDivisionError):
                            row[key] = finite(fn(spot,strike,years,iv,q=q,**extra))
        rows.append(row)
    return rows
