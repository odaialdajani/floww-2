#!/usr/bin/env python3
"""Validate read-only Liquid destination evidence; submission remains closed.

The discovered Computer order schema has no request-bound paper-mode field.
Status reads cannot eliminate a mode change between check and use. This module
contains no transport or credential access and cannot place or replay an order.
"""
import hashlib
import math
import re
from decimal import Decimal, InvalidOperation

POLICY = 'liquid-paper-capability-gate-v1'
ENDPOINT = 'https://coinvest-computer.liquid.trade/mcp'
MAX_AGE_SECONDS = 10
ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')


class PaperAdmissionError(ValueError):
    """Stable refusal code containing no account identifier or credential."""


def _refuse(reason):
    raise PaperAdmissionError(reason)


def _clock(value):
    if type(value) not in (int, float) or not 0 < value <= 100_000_000_000 or not math.isfinite(value):
        _refuse('invalid_evidence_clock')
    return value


def _wallet(value):
    if not isinstance(value, str) or not ADDRESS.fullmatch(value):
        _refuse('invalid_destination')
    return value.lower()


def _amount(value):
    if not isinstance(value, str) or len(value) > 64:
        _refuse('invalid_balance')
    try:
        number = Decimal(value)
    except InvalidOperation:
        _refuse('invalid_balance')
    if not number.is_finite():
        _refuse('invalid_balance')
    return number


def attest_destination(*, endpoint, account, portfolio, orders, observed_at, now):
    """Check one trusted transport read bundle, never grant order authority.

    Caller supplies authenticated structured results from one fixed native
    connection. Timestamp is the local read time; it is not a venue quote clock.
    Raw account identifiers are returned only as one-way receipt fingerprints.
    A successful result proves this read, not atomic mode binding or flatness
    after the read. Existing paper positions are preserved.
    """
    if endpoint != ENDPOINT:
        _refuse('unapproved_endpoint')
    age = _clock(now) - _clock(observed_at)
    if not 0 <= age <= MAX_AGE_SECONDS:
        _refuse('stale_or_future_destination')
    if any(not isinstance(value, dict) for value in (account, portfolio, orders)):
        _refuse('missing_destination_evidence')
    if account.get('addressRole') != 'trading-account':
        _refuse('unverified_account_role')
    wallet = _wallet(account.get('tradingAccountAddress'))
    if any(_wallet(value.get('wallet')) != wallet for value in (portfolio, orders)):
        _refuse('destination_mismatch')
    if any(value.get('paper') is not True for value in (portfolio, orders)):
        _refuse('paper_mode_unproven')
    statuses = portfolio.get('status'), orders.get('status')
    if any(not isinstance(value, dict) for value in statuses):
        _refuse('missing_fetch_status')
    if (statuses[0].get('account') != 'ok' or statuses[0].get('positions') != 'ok'
            or statuses[1].get('orders') != 'ok' or statuses[1].get('failedScopes') != []):
        _refuse('incomplete_destination_read')
    positions, resting = portfolio.get('positions'), orders.get('orders')
    if not isinstance(positions, list) or not isinstance(resting, list):
        _refuse('incomplete_destination_read')
    if len(positions) > 1000 or len(resting) > 1000:
        _refuse('destination_read_limit')
    balances = portfolio.get('account')
    if not isinstance(balances, dict):
        _refuse('missing_balance')
    for name in ('equity', 'margin_used', 'available_balance', 'account_value'):
        _amount(balances.get(name))
    if _amount(balances['margin_used']) < 0:
        _refuse('invalid_balance')
    return {'policy': POLICY, 'scope': 'authenticated_read_only', 'paper_observed': True,
            'destination_fingerprint': hashlib.sha256(wallet.encode()).hexdigest(),
            'observed_at': observed_at, 'age_seconds': age,
            'existing_positions': len(positions), 'resting_orders': len(resting),
            'commissioning_book_clear': not positions and not resting,
            'submission_enabled': False, 'automation_enabled': False,
            'reason': 'atomic_paper_mode_binding_unverified'}


def inspect_order_capability(tool):
    """Record the discovered contract gap; names/descriptions do not authorize it."""
    if not isinstance(tool, dict) or tool.get('name') != 'execute_order':
        _refuse('missing_order_schema')
    schema = tool.get('input_schema')
    if not isinstance(schema, dict) or not isinstance(schema.get('properties'), dict):
        _refuse('invalid_order_schema')
    return {'policy': POLICY, 'tool': 'execute_order', 'submission_enabled': False,
            'has_paper_parameter': 'executionMode' in schema['properties'],
            'reason': 'atomic_paper_mode_binding_unverified',
            'next_action': 'verify_server_enforced_simulated_destination_before_implementation'}


def submit_paper(intent, attestation):
    """Fail before persistence or transport until a reviewed venue contract exists.

    Neither caller JSON nor a research answer can activate this lane. Do not
    replace this with a status-then-order check or pass-through transport.
    """
    _refuse('paper_submission_not_commissioned')
