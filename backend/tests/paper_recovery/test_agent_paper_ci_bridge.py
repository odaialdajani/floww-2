"""CI bridge — core invariants of the prepared deterministic paper ledger.

The five repo-root suites (tests/test_agent_paper_*.py, 76 tests) exercise
services/agent/paper deeply but are NOT collected by backend CI (ci.yml runs
pytest from ./backend, so only backend/tests runs — backlog B9, an Architect
decision). Until that wiring decision lands, this file gives the backend gate
a compact, independent set of the ledger's strongest PURE invariants so a
backend change that breaks the deterministic ledger fails CI today:

  - simulated fills charge slippage/fees exactly once, in the chosen method
  - exact/derived refuse binary floats, out-of-range and inexact values
  - validate_json rejects floats, hostile keys, oversized ints, deep nesting
  - operation ids are version-bound and epoch-bound
  - digests bind canonical content (key-order independent)
  - a replayed source quote returns the ORIGINAL fill, never a new economic
    fill (the ledger's idempotency core)
  - clock rollback is refused
  - policy records are digest-bound; tampering is refused

This is a bridge, not a copy: deep valuation/risk/guard coverage stays in the
root suites. No Mongo, no network, no admission path is touched.
"""
from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.agent.paper.accounting import derived, exact, simulated_fill  # noqa: E402
from services.agent.paper.execution import (  # noqa: E402
    fill_order,
    new_book,
    stage_order,
)
from services.agent.paper.policy import SEMANTICS, create_policy, validate_policy  # noqa: E402
from services.agent.paper.repository import (  # noqa: E402
    MAX_VERSION,
    PaperConflict,
    digest,
    operation_id,
    operation_version,
    scope,
    validate_json,
)

NOW = datetime(2026, 10, 27, 14, tzinfo=UTC)
EPOCH = str(uuid.uuid4())


def _staged_book():
    state = new_book("1000", currency="USD")
    result, event = stage_order(
        state, epoch=EPOCH, contract_id="synthetic-option", product_kind="option",
        premium_factor="100", side="buy", quantity=2, limit="2.60", fee_per_unit="0.65",
        slippage_enabled=True, slippage_method="price", price_increment="0.05",
        max_quote_age_seconds=60, max_spread="0.20", latency_ms=0, now=NOW,
        order_expires_at=NOW + timedelta(minutes=10), proposal_digest="a" * 64,
        committed_version=1, currency="USD",
    )
    order_id = event["order_id"]
    return result, order_id


def _quote(source_id="q1", observed=None):
    observed = observed or NOW
    return {
        "contract_id": "synthetic-option", "source_id": source_id,
        "observed_at": observed.isoformat(), "received_at": observed.isoformat(),
        "bid": "2.40", "ask": "2.50", "bid_size": 10, "ask_size": 10,
        "size_unit": "contracts",
    }


class TestSimulatedFillArithmetic:
    def test_price_method_charges_slippage_once_in_price(self):
        fill = simulated_fill(1, "100", "2.00", "0.65", slippage_enabled=True,
                             slippage_method="price", price_increment="0.05")
        assert fill["fill_price"] == "2.05"
        assert fill["slippage_cash_charge"] == "0"
        assert Decimal(fill["cash_change"]) == Decimal("-205.65")  # -(1*100*2.05) - 0.65

    def test_cash_method_charges_slippage_once_in_cash(self):
        fill = simulated_fill(2, "100", "2.00", "0.65", slippage_enabled=True,
                             slippage_method="cash", price_increment="0.05")
        assert fill["fill_price"] == "2.00"
        assert Decimal(fill["slippage_cash_charge"]) == Decimal("10.00")  # 2*100*0.05, once
        assert Decimal(fill["cash_change"]) == Decimal("-410.65")  # -(400) - 0.65 - 10.00

    def test_off_keeps_price_and_removes_slippage(self):
        fill = simulated_fill(1, "100", "2.00", "0.65", slippage_enabled=False,
                             slippage_method="cash", price_increment="0.05")
        assert fill["fill_price"] == "2.00"
        assert fill["slippage_cash_charge"] == "0"
        assert fill["effective_slippage_mode"] == "off"


class TestExactArithmetic:
    def test_floats_never_enter_the_book(self):
        with pytest.raises(ValueError):
            exact(1.5)

    def test_out_of_precision_refused(self):
        with pytest.raises(ValueError):
            exact("1." + "9" * 40)

    def test_inexact_derivation_refused(self):
        with pytest.raises(ValueError):
            derived("1" * 600)

    def test_accepted_scales_stay_exact(self):
        # Accepted envelope: up to 28 significant digits AND adjusted
        # exponent within +/-24 (accounting.ARITHMETIC_PRECISION comment).
        value = exact("123456789012345678901234.5678")  # 28 digits, 1.23e23
        assert str(value) == "123456789012345678901234.5678"
        # ... and a 29-digit value is out of the supported envelope.
        with pytest.raises(ValueError):
            exact("1.2345678901234567890123456789")  # 29 significant digits


class TestValidateJson:
    def test_floats_refused_everywhere(self):
        with pytest.raises(ValueError):
            validate_json({"a": {"b": 1.5}})

    def test_hostile_keys_refused(self):
        for key in ("$bad", "a.b", "", "a\x00b"):
            with pytest.raises(ValueError):
                validate_json({key: 1})

    def test_oversized_integers_refused(self):
        with pytest.raises(ValueError):
            validate_json({"a": 2**63})
        assert validate_json({"a": 2**63 - 1})["a"] == 2**63 - 1

    def test_deep_nesting_refused(self):
        deep = {"a": 1}
        for _ in range(30):
            deep = {"a": deep}
        with pytest.raises(ValueError):
            validate_json(deep)

    def test_canonical_round_trip_is_key_order_free(self):
        assert validate_json({"b": 1, "a": [1, "x"]}) == {"a": [1, "x"], "b": 1}


class TestOperationIdentity:
    def test_operation_id_is_version_and_epoch_bound(self):
        epoch, nonce = str(uuid.uuid4()), str(uuid.uuid4())
        op = operation_id(7, nonce, epoch=epoch)
        assert operation_version(op) == 7
        assert op.startswith(f"{epoch}:7:")

    def test_bad_shapes_refused(self):
        with pytest.raises(ValueError):
            operation_id(-1, epoch=EPOCH)
        with pytest.raises(ValueError):
            operation_id(MAX_VERSION + 1, epoch=EPOCH)
        with pytest.raises(ValueError):
            operation_version("not-an-operation")

    def test_scope_only_accepts_internal_venue(self):
        owner, account = str(uuid.uuid4()), str(uuid.uuid4())
        assert scope(owner, account, "internal")["venue"] == "internal"
        with pytest.raises(ValueError):
            scope(owner, account, "alpaca")


class TestDigestBindsContent:
    def test_key_order_does_not_change_digest(self):
        assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})

    def test_content_change_changes_digest(self):
        assert digest({"a": 1}) != digest({"a": 2})


class TestQuoteReplayIdempotency:
    def test_replayed_quote_returns_the_original_fill(self):
        state, order_id = _staged_book()
        state, first, changed = fill_order(state, order_id, _quote(), now=NOW, committed_version=2)
        assert changed is True
        state, replay, changed = fill_order(state, order_id, _quote(), now=NOW, committed_version=3)
        assert changed is False
        assert replay == first, "a replayed source quote must return the original receipt"

    def test_clock_rollback_refused(self):
        state, order_id = _staged_book()
        with pytest.raises(ValueError):
            fill_order(state, order_id, _quote(), now=NOW - timedelta(seconds=1), committed_version=2)


class TestPolicyRecordIntegrity:
    def _record(self):
        owner, account = str(uuid.uuid4()), str(uuid.uuid4())
        binding = {**scope(owner, account, "internal"), "epoch": str(uuid.uuid4())}
        body = {**SEMANTICS, "currency": "USD",
                "limits": {"per_trade_max_loss": "500", "daily_loss_limit": "1000",
                           "observed_drawdown_limit": "800", "max_committed_exposure": "5000"},
                "valuation": {"mark_method": "bid", "max_mark_age_seconds": 30,
                              "max_spread": "0.50"}}
        record = create_policy(binding, body, policy_id=str(uuid.uuid4()), policy_version=1,
                               effective_at=NOW, accepted_at=NOW - timedelta(minutes=1),
                               accepted_by=owner, acceptance_evidence=["owner-chat-20261027"],
                               now=NOW, verify_acceptance=lambda r: True)
        return binding, record

    def test_digest_binds_policy_content(self):
        binding, record = self._record()
        assert record["digest"] == digest({k: v for k, v in record.items() if k != "digest"})
        assert validate_policy(record, binding, now=NOW) == record

    def test_tampered_policy_refused(self):
        binding, record = self._record()
        tampered = {**record, "body": {**record["body"],
                                      "limits": {**record["body"]["limits"],
                                                 "daily_loss_limit": "99999"}}}
        with pytest.raises((PaperConflict, ValueError)):
            validate_policy(tampered, binding, now=NOW)
