"""Synthetic, explicit policies; these figures are not account recommendations."""

import copy
import sys
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.agent.paper.accounting import derived  # noqa: E402
from services.agent.paper.execution import new_book  # noqa: E402
from services.agent.paper.policy import (  # noqa: E402
    SEMANTICS,
    create_policy,
    prepare_policy_change,
    validate_policy,
    valuation_policy,
)
from services.agent.paper.repository import digest  # noqa: E402
from services.agent.paper.risk import (  # noqa: E402
    create_trade_evidence,
    metadata_digests,
    prepare_fill,
    prepare_stage,
)

NOW = datetime(2026, 9, 25, 14, tzinfo=UTC)
CONTRACT = "TEST261016C00100000"


def policy_fixture(*, changes=None):
    binding = dict(owner=str(uuid.uuid4()), account_id=str(uuid.uuid4()), venue="internal", epoch=str(uuid.uuid4()))
    body = {**SEMANTICS, "currency": "USD",
            "limits": dict(per_trade_max_loss="600", daily_loss_limit="100", observed_drawdown_limit="100",
                           max_committed_exposure="900"),
            "valuation": dict(mark_method="bid", max_mark_age_seconds=60, max_spread="0.5")}
    body["limits"].update(changes or {})
    policy = create_policy(binding, body, policy_id=str(uuid.uuid4()), policy_version=1, effective_at=NOW,
                           accepted_at=NOW, accepted_by=binding["owner"], acceptance_evidence=["synthetic-owner-choice"],
                           now=NOW, verify_acceptance=lambda record: True)
    account = dict(**binding, version=0, state=new_book("1000", currency="USD"), recovery_pending=False)
    state, _ = prepare_policy_change(account, policy, expected_version=0, expected_policy_digest=None, now=NOW)
    account.update(state=state, version=1)
    return account, policy


def parameters(method="price", **changes):
    return dict(contract_id=CONTRACT, product_kind="option", premium_factor="100", side="buy", quantity=2,
                limit="2.10", fee_per_unit="0.65", slippage_enabled=True, slippage_method=method,
                price_increment="0.05", max_quote_age_seconds=60, max_spread="0.5", latency_ms=0,
                order_expires_at=(NOW+timedelta(minutes=10)).isoformat(), proposal_digest="a"*64, currency="USD", **changes)


def evidence_fixture(account, policy, params, *, maximum=None, exit_cost="6", lifecycle="1", valid_until=None):
    # Literal independent oracles for the declared two-contract example.
    max_loss = maximum or ("435.30" if params["slippage_method"] == "price" else "445.30")
    return create_trade_evidence({key: account[key] for key in ("owner", "account_id", "venue", "epoch")},
                                policy, params,
                                dict(exit_cost_per_unit=exit_cost, lifecycle_cost_per_unit=lifecycle,
                                     maximum_loss=max_loss, maximum_loss_basis="prepaid_long_zero_recovery_plus_costs",
                                     cost_basis="linear_per_unit",
                                     contract_digest=metadata_digests(frame_fixture(policy)["metadata"][0])[0],
                                     lifecycle_digest=metadata_digests(frame_fixture(policy)["metadata"][0])[1]),
                                proposal_version=1, evidence=["synthetic-contract", "synthetic-lifecycle"],
                                verified_at=NOW, valid_until=valid_until or NOW+timedelta(hours=1),
                                verifier_version="independent-fixture-v1", now=NOW, verify_evidence=lambda value: True)


def frame_fixture(policy, *, now=NOW, bid="1.90", ask="2.00", opening="1000"):
    return dict(policy=valuation_policy(policy),
                session=dict(session_id="XNYS-2026-09-25", calendar_version="fixture-1", source_id="fixture-session",
                             opened_at="2026-09-25T13:30:00+00:00", closed_at="2026-09-25T20:00:00+00:00"),
                session_open=dict(session_id="XNYS-2026-09-25", source_id="fixture-open",
                                  observed_at="2026-09-25T13:30:00+00:00", equity=opening),
                marks=[dict(contract_id=CONTRACT, currency="USD", source_id="fixture-mark-"+now.isoformat(),
                            observed_at=now.isoformat(), received_at=now.isoformat(), bid=bid, ask=ask)],
                metadata=[dict(contract_id=CONTRACT, source_id="fixture-contract", verified_at=NOW.isoformat(),
                               currency="USD", product_kind="option", premium_factor="100", adjusted=False,
                               right="call", strike="100", underlying="TEST", exercise_style="european",
                               settlement_style="cash", deliverable=dict(kind="cash", quantity="100", currency="USD"),
                               last_trade_at="2026-10-16T20:00:00+00:00", expiry_at="2026-10-16T20:00:00+00:00",
                               exercise_cutoff_at="2026-10-16T21:00:00+00:00", settlement_at="2026-10-17T20:00:00+00:00")])


def quote_fixture(*, now=NOW+timedelta(seconds=1), source="fixture-fill", bid="1.90", ask="2.00", size=1):
    return dict(contract_id=CONTRACT, source_id=source, observed_at=now.isoformat(), received_at=now.isoformat(),
                bid=bid, ask=ask, bid_size=size, ask_size=size, size_unit="contracts")


def accepted(account, result):
    if result["status"] != "pass":
        raise AssertionError(result)
    return {**account, "version": account["version"]+1, "state": result["state"]}


class PaperRiskTests(unittest.TestCase):
    def staged(self, method="price", changes=None):
        account, policy = policy_fixture(changes=changes)
        params = parameters(method)
        evidence = evidence_fixture(account, policy, params)
        result = prepare_stage(account, params, expected_version=1, trade_evidence=evidence,
                               frame=frame_fixture(policy), now=NOW)
        return account, policy, params, evidence, result

    def test_policy_has_no_default_limits_or_acceptance(self):
        account, policy = policy_fixture()
        self.assertFalse(prepare_policy_change({**account, "version": 0, "state": new_book("1000", currency="USD")},
                                              policy, expected_version=0, expected_policy_digest=None, now=NOW)[1]["admission_allowed"])
        args = dict(policy_id=policy["policy_id"], policy_version=1, effective_at=NOW, accepted_at=NOW,
                    accepted_by=account["owner"], acceptance_evidence=["fixture"], now=NOW, verify_acceptance=lambda _: True)
        for missing in policy["body"]["limits"]:
            body = copy.deepcopy(policy["body"])
            del body["limits"][missing]
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                create_policy(policy["binding"], body, **args)
        for verifier in (None, lambda _: False, lambda _: 1):
            with self.assertRaises(ValueError):
                create_policy(policy["binding"], policy["body"], **{**args, "verify_acceptance": verifier})

    def test_policy_is_detached_hash_checked_and_owner_bound(self):
        account, policy = policy_fixture()
        other = {**policy["binding"], "owner": str(uuid.uuid4())}
        with self.assertRaises(ValueError):
            validate_policy(policy, other, now=NOW)
        changed = copy.deepcopy(policy)
        changed["body"]["limits"]["daily_loss_limit"] = "999"
        with self.assertRaises(ValueError):
            validate_policy(changed, policy["binding"], now=NOW)
        self.assertEqual(account["state"]["risk_policy"]["body"]["limits"]["daily_loss_limit"], "100")

    def test_policy_change_preserves_risk_anchor_and_requires_sequence(self):
        account, prior = policy_fixture()
        account["state"]["valuation"] = {"risk_anchor": {"observed_peak_equity": "1200", "baseline_equity": "1000"}}
        next_policy = create_policy(prior["binding"], prior["body"], policy_id=prior["policy_id"], policy_version=2,
                                    effective_at=NOW, accepted_at=NOW, accepted_by=account["owner"],
                                    acceptance_evidence=["fixture-second-choice"], now=NOW, verify_acceptance=lambda _: True)
        state, _ = prepare_policy_change(account, next_policy, expected_version=1,
                                         expected_policy_digest=prior["digest"], now=NOW)
        self.assertEqual(state["valuation"], account["state"]["valuation"])
        with self.assertRaises(ValueError):
            prepare_policy_change(account, next_policy, expected_version=1, expected_policy_digest="wrong", now=NOW)

    def test_stage_and_partial_fill_keep_reservations_out_of_equity(self):
        for method, reserve, remainder, free in (("price", "421.30", "210.65", "569.70"),
                                               ("cash", "431.30", "215.65", "564.70")):
            with self.subTest(method=method):
                account, policy, _, _, stage = self.staged(method)
                self.assertEqual(stage["status"], "pass", stage)
                self.assertFalse(stage["admission_allowed"])
                self.assertEqual(stage["decision"]["equity_after"], "1000")
                self.assertEqual(stage["decision"]["after"]["entry_reservations"], reserve)
                self.assertEqual(stage["decision"]["after"]["cost_buffers"], "14")
                order = stage["event"]["order_id"]
                staged = accepted(account, stage)
                filled = prepare_fill(staged, order, quote_fixture(), expected_version=2,
                                      frame=frame_fixture(policy, now=NOW+timedelta(seconds=1)), now=NOW+timedelta(seconds=1))
                self.assertEqual(filled["status"], "pass", filled)
                self.assertEqual(filled["state"]["cash"], "794.35")
                self.assertEqual(filled["decision"]["equity_after"], "984.35")
                self.assertEqual(filled["decision"]["after"]["entry_reservations"], remainder)
                self.assertEqual(filled["decision"]["after"]["available_cash"], free)

    def test_stage_refusal_never_changes_caller_state(self):
        account, policy, params, evidence, _ = self.staged(changes={"per_trade_max_loss": "435.29"})
        before = copy.deepcopy(account)
        result = prepare_stage(account, params, expected_version=1, trade_evidence=evidence,
                               frame=frame_fixture(policy), now=NOW)
        self.assertEqual(result["status"], "refuse")
        self.assertIsNone(result["state"])
        self.assertEqual(account, before)

    def test_cost_buffers_cannot_spend_the_last_cash(self):
        account, policy, params, evidence, _ = self.staged()
        account["state"]["cash"] = "430"
        result = prepare_stage(account, params, expected_version=1, trade_evidence=evidence,
                               frame=frame_fixture(policy, opening="430"), now=NOW)
        self.assertEqual(result["status"], "refuse")
        self.assertIn("cost buffers", result["reason"])

    def test_missing_unknown_costs_and_fabricated_maximum_loss_refuse_record(self):
        account, policy = policy_fixture()
        for cost in (None, True, "-1"):
            with self.subTest(cost=cost), self.assertRaises(ValueError):
                evidence_fixture(account, policy, parameters(), exit_cost=cost)
        with self.assertRaises(ValueError):
            evidence_fixture(account, policy, parameters(), maximum="421.30")
        result = prepare_stage(account, parameters(), expected_version=1, trade_evidence=None,
                               frame=frame_fixture(policy), now=NOW)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["state"])

    def test_limits_have_explicit_boundaries_and_zero_stops_entries(self):
        for changes, expected in (({"per_trade_max_loss": "435.30", "max_committed_exposure": "435.30"}, "pass"),
                                  ({"max_committed_exposure": "435.29"}, "refuse"),
                                  ({"daily_loss_limit": "0"}, "refuse"),
                                  ({"observed_drawdown_limit": "0"}, "refuse")):
            with self.subTest(changes=changes):
                self.assertEqual(self.staged(changes=changes)[4]["status"], expected)

    def test_later_fill_rechecks_loss_instead_of_reusing_stage_result(self):
        account, policy, _, _, stage = self.staged(changes={"daily_loss_limit": "10"})
        staged = accepted(account, stage)
        result = prepare_fill(staged, stage["event"]["order_id"], quote_fixture(), expected_version=2,
                              frame=frame_fixture(policy, now=NOW+timedelta(seconds=1)), now=NOW+timedelta(seconds=1))
        self.assertEqual(result["status"], "refuse")
        self.assertIsNone(result["state"])
        self.assertEqual(staged["state"]["cash"], "1000")

    def test_missing_stale_marks_or_expired_evidence_do_not_fill(self):
        account, policy, _, _, stage = self.staged()
        staged = accepted(account, stage)
        for frame in (frame_fixture(policy), {**frame_fixture(policy), "marks": []}):
            result = prepare_fill(staged, stage["event"]["order_id"], quote_fixture(now=NOW+timedelta(seconds=61)),
                                  expected_version=2, frame=frame, now=NOW+timedelta(seconds=61))
            self.assertEqual(result["status"], "unknown")
            self.assertIsNone(result["state"])
        expired = copy.deepcopy(staged)
        record = expired["state"]["risk_trades"][stage["event"]["structure_id"]]
        record["valid_until"] = (NOW+timedelta(seconds=1)).isoformat()
        record["digest"] = digest({key: value for key, value in record.items() if key != "digest"})
        result = prepare_fill(expired, stage["event"]["order_id"], quote_fixture(now=NOW+timedelta(seconds=2)),
                              expected_version=2, frame=frame_fixture(policy, now=NOW+timedelta(seconds=2)),
                              now=NOW+timedelta(seconds=2))
        self.assertEqual(result["status"], "unknown")

    def test_wrong_version_owner_and_policy_frame_refuse_without_mutation(self):
        account, policy, params, evidence, _ = self.staged()
        wrong = copy.deepcopy(evidence)
        wrong["binding"]["account_id"] = str(uuid.uuid4())
        wrong["digest"] = digest({key: value for key, value in wrong.items() if key != "digest"})
        frames = [frame_fixture(policy), {**frame_fixture(policy), "policy": {}}]
        for version, record, frame in ((2, evidence, frames[0]), (1, wrong, frames[0]), (1, evidence, frames[1])):
            result = prepare_stage(account, params, expected_version=version, trade_evidence=record, frame=frame, now=NOW)
            self.assertEqual(result["status"], "unknown")
            self.assertIsNone(result["state"])

    def test_evidence_economics_cannot_be_reused_for_larger_quantity(self):
        account, policy, params, evidence, _ = self.staged()
        result = prepare_stage(account, {**params, "quantity": 3}, expected_version=1, trade_evidence=evidence,
                               frame=frame_fixture(policy), now=NOW)
        self.assertEqual(result["status"], "unknown")

    def test_partial_fill_releases_only_filled_principal_not_future_costs(self):
        account, policy, _, _, stage = self.staged()
        staged = accepted(account, stage)
        result = prepare_fill(staged, stage["event"]["order_id"], quote_fixture(), expected_version=2,
                              frame=frame_fixture(policy, now=NOW+timedelta(seconds=1)), now=NOW+timedelta(seconds=1))
        filled = accepted(staged, result)
        self.assertEqual(result["decision"]["after"]["cost_buffers"], "14")
        duplicate = prepare_fill(filled, stage["event"]["order_id"], quote_fixture(), expected_version=3,
                                 frame=frame_fixture(policy, now=NOW+timedelta(seconds=1)), now=NOW+timedelta(seconds=1))
        self.assertEqual(duplicate["status"], "unchanged")
        self.assertIsNone(duplicate["state"])
        self.assertEqual(derived(filled["state"]["cash"]), derived("794.35"))


    def test_changed_contract_terms_are_unknown_at_stage_and_later_fill(self):
        changes = [dict(right="put"), dict(strike="1000"), dict(underlying="DIFFERENT"),
                   dict(settlement_style="physical", deliverable=dict(kind="shares", quantity="100", symbol="TEST", currency="USD")),
                   dict(exercise_cutoff_at="2026-10-16T22:00:00+00:00")]
        account, policy, params, evidence, stage = self.staged()
        staged = accepted(account, stage)
        for changed in changes:
            with self.subTest(changed=changed):
                frame = frame_fixture(policy)
                frame["metadata"][0].update(changed)
                result = prepare_stage(account, params, expected_version=1, trade_evidence=evidence, frame=frame, now=NOW)
                self.assertEqual(result["status"], "unknown", result)
                self.assertIsNone(result["state"])
                frame = frame_fixture(policy, now=NOW+timedelta(seconds=1))
                frame["metadata"][0].update(changed)
                result = prepare_fill(staged, stage["event"]["order_id"], quote_fixture(), expected_version=2,
                                      frame=frame, now=NOW+timedelta(seconds=1))
                self.assertEqual(result["status"], "unknown", result)
                self.assertIsNone(result["state"])

    def test_pending_only_entry_requires_current_contract_and_lifecycle_content(self):
        account, policy, params, evidence, _ = self.staged()
        for change in ("missing", "due", "wrong_lifecycle_hash"):
            frame, record = frame_fixture(policy), copy.deepcopy(evidence)
            if change == "missing":
                frame["metadata"] = []
            elif change == "due":
                frame["metadata"][0]["last_trade_at"] = NOW.isoformat()
                record["costs"]["contract_digest"], record["costs"]["lifecycle_digest"] = metadata_digests(frame["metadata"][0])
            else:
                record["costs"]["lifecycle_digest"] = "d"*64
            record["digest"] = digest({key: value for key, value in record.items() if key != "digest"})
            result = prepare_stage(account, params, expected_version=1, trade_evidence=record, frame=frame, now=NOW)
            self.assertEqual(result["status"], "unknown", result)
            self.assertIsNone(result["state"])

    def test_pending_metadata_deadline_bounds_decision(self):
        account, policy, params, evidence, _ = self.staged()
        frame = frame_fixture(policy)
        deadline = (NOW+timedelta(seconds=10)).isoformat()
        frame["metadata"][0]["last_trade_at"] = deadline
        evidence["costs"]["contract_digest"], evidence["costs"]["lifecycle_digest"] = metadata_digests(frame["metadata"][0])
        evidence["digest"] = digest({key: value for key, value in evidence.items() if key != "digest"})
        result = prepare_stage(account, params, expected_version=1, trade_evidence=evidence, frame=frame, now=NOW)
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["decision"]["valid_until"], deadline)

    def test_reducing_exit_survives_loss_breach_with_known_bounded_costs(self):
        for method in ("price", "cash"):
            account, policy, params, _, stage = self.staged(method)
            staged = accepted(account, stage)
            at = NOW+timedelta(seconds=1)
            full = prepare_fill(staged, stage["event"]["order_id"], quote_fixture(size=2), expected_version=2,
                                frame=frame_fixture(policy, now=at), now=at)
            held = accepted(staged, full)
            closing = {**params, "side": "sell", "quantity": 1, "limit": "0.40", "structure_id": stage["event"]["structure_id"]}
            at = NOW+timedelta(seconds=2)
            close = prepare_stage(held, closing, expected_version=3, trade_evidence=None,
                                  frame=frame_fixture(policy, now=at, bid="0.50", ask="0.60"), now=at)
            self.assertEqual(close["status"], "pass", close)
            self.assertEqual(close["decision"]["loss_from_open"], "311.30")
            closing_account = accepted(held, close)
            at = NOW+timedelta(seconds=3)
            done = prepare_fill(closing_account, close["event"]["order_id"],
                                quote_fixture(now=at, bid="0.50", ask="0.60", source="close-fill"), expected_version=4,
                                frame=frame_fixture(policy, now=at, bid="0.50", ask="0.60"), now=at)
            self.assertEqual(done["status"], "pass", done)
            self.assertEqual(done["state"]["cash"], "633.05")
            self.assertEqual(done["decision"]["after"]["cost_buffers"], "7")
            self.assertEqual(done["decision"]["after"]["committed_exposure"], "57.00")
            self.assertFalse(done["admission_allowed"])
            too_costly = {**closing, "fee_per_unit": "1000"}
            refused = prepare_stage(held, too_costly, expected_version=3, trade_evidence=None,
                                    frame=frame_fixture(policy, now=at, bid="0.50", ask="0.60"), now=at)
            self.assertEqual(refused["status"], "refuse", refused)
            self.assertIsNone(refused["state"])

    def test_changed_saved_reservation_refuses_fill(self):
        account, policy, _, _, stage = self.staged()
        staged = accepted(account, stage)
        staged["state"]["orders"][stage["event"]["order_id"]]["reserved_cash"] = "0"
        result = prepare_fill(staged, stage["event"]["order_id"], quote_fixture(), expected_version=2,
                              frame=frame_fixture(policy, now=NOW+timedelta(seconds=1)), now=NOW+timedelta(seconds=1))
        self.assertEqual(result["status"], "unknown", result)
        self.assertIsNone(result["state"])

    def test_low_ambient_precision_cannot_round_risk(self):
        from decimal import localcontext
        with localcontext() as context:
            context.prec = 6
            account, policy, _, _, stage = self.staged("cash")
            staged = accepted(account, stage)
            result = prepare_fill(staged, stage["event"]["order_id"], quote_fixture(), expected_version=2,
                                  frame=frame_fixture(policy, now=NOW+timedelta(seconds=1)), now=NOW+timedelta(seconds=1))
        self.assertEqual(result["status"], "pass", result)
        self.assertEqual(result["decision"]["equity_after"], "984.35")
        self.assertEqual(result["decision"]["after"]["available_cash"], "564.70")


if __name__ == "__main__":
    unittest.main()
