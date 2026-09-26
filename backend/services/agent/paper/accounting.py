"""Exact paper arithmetic under the configurable owner decision in ADR-0010.

This module alone enables no account/order path. Historical backtest arithmetic
is neither imported nor modified. Executable-quote/risk/lifecycle validation is
required in the future admission service, independently of this arithmetic.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, DecimalException, Inexact, InvalidOperation, localcontext

MAX_HOLDINGS = 128
ARITHMETIC_PRECISION = 256  # Exact across the accepted 28-digit, +/-24 exponent range.


@contextmanager
def exact_context():
    """Derived balances may grow; refuse rather than silently lose money digits."""
    try:
        with localcontext() as context:
            context.prec = ARITHMETIC_PRECISION
            context.traps[Inexact] = True
            yield context
    except DecimalException:
        raise ValueError("Paper arithmetic exceeds exact supported precision") from None


def derived(value):
    """Read bounded exact results without reapplying raw-input precision limits."""
    if type(value) not in (str, int, Decimal) or isinstance(value, str) and len(value) > 512:
        raise ValueError("Invalid derived decimal")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid derived decimal") from None
    if not result.is_finite() or abs(result.adjusted()) > 200 or len(result.as_tuple().digits) > 256:
        raise ValueError("Derived decimal exceeds arithmetic bounds")
    return result

def exact(value, *, nonnegative=False, positive=False):
    if type(value) not in (str, int, Decimal):
        raise ValueError("Use exact decimal strings, integers or Decimal values")
    if isinstance(value, str) and len(value) > 128:
        raise ValueError("Decimal input exceeds supported length")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid decimal value") from None
    if not result.is_finite() or abs(result.adjusted()) > 24 or len(result.as_tuple().digits) > 28:
        raise ValueError("Decimal value is nonfinite or outside supported precision")
    if nonnegative and result < 0 or positive and result <= 0:
        raise ValueError("Decimal value has an invalid sign")
    return result


def fill_cash_change(signed_quantity, premium_factor, fill_price, explicit_fee):
    quantity = exact(signed_quantity)
    factor = exact(premium_factor, positive=True)
    price = exact(fill_price, nonnegative=True)
    fee = derived(explicit_fee)
    if fee < 0:
        raise ValueError("Fee cannot be negative")
    if not quantity:
        raise ValueError("A zero quantity is not a fill")
    with exact_context() as context:
        context.prec = ARITHMETIC_PRECISION
        return -quantity * factor * price - fee


def simulated_fill(signed_quantity, premium_factor, reference_price, explicit_fee,
                   *, slippage_enabled, slippage_method, price_increment):
    """Freeze the selected setting in the fill; adverse cost is charged once.

The caller supplies an eligible executable reference and a declared per-price-
unit adverse increment. It may not use a theoretical price or imply midpoint
execution. No default setting or slippage estimate is invented here.
"""
    if type(slippage_enabled) is not bool or slippage_method not in ("price", "cash"):
        raise ValueError("Explicit slippage on/off and charging method are required")
    quantity = exact(signed_quantity)
    factor = exact(premium_factor, positive=True)
    reference = exact(reference_price, nonnegative=True)
    fee = derived(explicit_fee)
    if fee < 0:
        raise ValueError("Fee cannot be negative")
    increment = exact(price_increment, nonnegative=True)
    if quantity == 0:
        raise ValueError("A zero quantity is not a fill")
    if slippage_enabled and quantity < 0 and increment > reference:
        raise ValueError("Adverse effective sell price would be negative")
    with exact_context() as context:
        context.prec = ARITHMETIC_PRECISION
        fill_price = reference
        cash_charge = Decimal(0)
        mode = slippage_method if slippage_enabled else "off"
        if mode == "price":
            fill_price += increment if quantity > 0 else -increment
            if fill_price < 0:
                raise ValueError("Adverse fill price would be negative")
        elif mode == "cash":
            cash_charge = abs(quantity) * factor * increment
        # All inputs were checked above; fill_price is an exact derived value.
        cash_change = -quantity * factor * fill_price - fee - cash_charge
        return dict(quantity=str(quantity), premium_factor=str(factor),
                    reference_price=str(reference), fill_price=str(fill_price), explicit_fee=str(fee),
                    slippage_enabled=slippage_enabled, slippage_method=slippage_method,
                    effective_slippage_mode=mode, price_increment=str(increment),
                    slippage_cash_charge=str(cash_charge), cash_change=str(cash_change),
                    accounting_version="paper-configurable-slippage-1")


def marked_value(signed_quantity, premium_factor, mark_price):
    with exact_context() as context:
        context.prec = ARITHMETIC_PRECISION
        return exact(signed_quantity) * exact(premium_factor, positive=True) * exact(mark_price, nonnegative=True)


def equity(cash, holdings):
    """Every holding must carry a known mark; unknowns cannot become zero."""
    with exact_context() as context:
        context.prec = ARITHMETIC_PRECISION
        total = derived(cash)
        for index, holding in enumerate(holdings):
            if index >= MAX_HOLDINGS:
                raise ValueError("Marked holdings exceed the supported account limit")
            total += marked_value(holding["quantity"], holding["premium_factor"], holding["mark"])
        return total
