"""Funded observation invariants with exact independent cash/risk expectations."""
import copy
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_agent_paper_risk import (  # noqa: E402
    NOW, accepted, evidence_fixture, frame_fixture, parameters, policy_fixture, quote_fixture,
)
from services.agent.paper.policy import binding_of  # noqa: E402
from services.agent.paper.repository import PaperCapacity, PaperConflict, operation_id  # noqa: E402
from services.agent.paper.risk import prepare_fill, prepare_stage  # noqa: E402
from services.agent.paper.risk_assessment import (  # noqa: E402
    EXIT_ASSESSMENT_CREDITS, begin, finalize, new_control, replenish, reserved_events,
)
from services.agent.paper.valuation import book_digest, current_observation, observe  # noqa: E402


class GuardedAssessmentTests(unittest.TestCase):
    def account(self):
        account, policy = policy_fixture()
        account["state"]["risk_control"] = new_control()
        return account, policy

    def intent(self, account, policy, *, now=NOW, frame=None, action="entry", structure=None):
        frame = frame or frame_fixture(policy, now=now)
        request = operation_id(account["version"], epoch=account["epoch"])
        terms = parameters()
        evidence = evidence_fixture(account, policy, terms)
        if action == "reduce":
            terms = {**terms, "side": "sell", "quantity": 1, "limit": "0.40", "structure_id": structure}
            evidence = None
        state, event = begin(account, request, {"frame": frame, "parameters": terms, "evidence": evidence},
                             action=action, structure_id=structure, now=now)
        return {**account, "state": state, "version": account["version"]+1}, request, event, frame

    def held(self):
        account, policy = policy_fixture()
        params = parameters()
        record = evidence_fixture(account, policy, params)
        stage = prepare_stage(account, params, expected_version=account["version"], trade_evidence=record,
                               frame=frame_fixture(policy), now=NOW)
        staged = accepted(account, stage)
        at = NOW+timedelta(seconds=1)
        filled = prepare_fill(staged, stage["event"]["order_id"], quote_fixture(now=at, size=2),
                              expected_version=staged["version"], frame=frame_fixture(policy, now=at), now=at)
        held = accepted(staged, filled)
        held["state"]["risk_control"] = new_control()
        structure = stage["event"]["structure_id"]
        held["state"]["risk_control"]["exit_credits"][structure] = EXIT_ASSESSMENT_CREDITS
        return held, policy, params, record, structure

    def test_begin_precedes_evaluation_preserves_exact_historical_basis_and_money(self):
        account, policy = self.account()
        old = copy.deepcopy(account)
        begun, request, _, _ = self.intent(account, policy)
        intent = begun["state"]["risk_control"]["pending"][request]
        self.assertEqual(account, old)
        self.assertEqual(intent["source_book_digest"], book_digest(old["state"]))
        self.assertEqual(intent["basis"]["cash"], "1000")
        self.assertNotIn("risk_control", intent["basis"])
        self.assertEqual(begun["state"]["cash"], "1000")
        self.assertEqual(reserved_events(old["state"]), 2)
        self.assertEqual(reserved_events(begun["state"]), 1)
        self.assertNotIn("valuation", begun["state"])
        with self.assertRaises(PaperConflict):
            self.intent(begun, policy)

    def test_refused_entry_saves_real_peak_and_later_drawdown_is_160(self):
        held, policy, params, record, _ = self.held()
        at = NOW+timedelta(seconds=2)
        frame = frame_fixture(policy, now=at, bid="3.00", ask="3.10")
        begun, request, _, _ = self.intent(held, policy, now=at, frame=frame)
        actual = observe(begun["state"], frame, now=at, binding=binding_of(begun), previous=begun["state"].get("valuation"))
        self.assertEqual(actual["equity"], "1188.70")
        result = prepare_stage(begun, params, expected_version=begun["version"], trade_evidence=record, frame=frame, now=at)
        self.assertEqual(result["status"], "refuse", result)
        state, event = finalize(begun, request, result, actual, now=at)
        resolved = {**begun, "state": state, "version": begun["version"]+1}
        self.assertEqual(state["cash"], "588.70")
        self.assertEqual(state["valuation"]["risk_anchor"]["observed_peak_equity"], "1188.70")
        self.assertEqual(event["actual_before"]["equity"], "1188.70")
        self.assertEqual(current_observation(resolved, now=at)["status"], "current")
        at = NOW+timedelta(seconds=3)
        # A real caller must verify projection before this pure replenishment.
        state, _ = replenish(resolved["state"], now=at)
        ready = {**resolved, "state": state, "version": resolved["version"]+1}
        frame = frame_fixture(policy, now=at, bid="2.20", ask="2.30")
        later, _, _, _ = self.intent(ready, policy, now=at, frame=frame)
        actual = observe(later["state"], frame, now=at, binding=binding_of(later), previous=later["state"].get("valuation"))
        self.assertEqual(actual["risk"]["observed_drawdown"], "160.00")
        result = prepare_stage(later, params, expected_version=later["version"], trade_evidence=record, frame=frame, now=at)
        self.assertEqual(result["status"], "refuse", result)

    def test_passed_candidate_keeps_valuation_bound_after_control_changes(self):
        account, policy = self.account()
        begun, request, _, frame = self.intent(account, policy)
        params = parameters()
        record = evidence_fixture(account, policy, params)
        actual = observe(begun["state"], frame, now=NOW, binding=binding_of(begun))
        result = prepare_stage(begun, params, expected_version=begun["version"], trade_evidence=record, frame=frame, now=NOW)
        self.assertEqual(result["status"], "pass", result)
        state, event = finalize(begun, request, result, actual, now=NOW)
        resolved = {**begun, "state": state, "version": begun["version"]+1}
        self.assertEqual(reserved_events(state), 39)
        self.assertEqual(current_observation(resolved, now=NOW)["status"], "current")
        self.assertEqual(event["risk_decision"]["after_book_digest"], book_digest(state))
        self.assertFalse(state["risk_control"]["pending"])
        self.assertEqual(state["risk_control"]["entry_credits"], 0)
        with self.assertRaises(PaperCapacity):
            self.intent(resolved, policy)

    def test_overlapping_exit_keeps_old_intent_and_prevents_silent_rebase(self):
        held, policy, _, _, structure = self.held()
        at = NOW+timedelta(seconds=2)
        first, entry_request, _, _ = self.intent(held, policy, now=at)
        reducing, exit_request, _, _ = self.intent(first, policy, now=at, action="reduce", structure=structure)
        self.assertEqual(set(reducing["state"]["risk_control"]["pending"]), {entry_request, exit_request})
        with self.assertRaises(PaperConflict):
            finalize(reducing, entry_request, {"status": "refuse"}, None, now=at)
        refused = {"status": "refuse", "reason": "synthetic known excessive cost"}
        actual = observe(reducing["state"], frame_fixture(policy, now=at), now=at, binding=binding_of(reducing),
                         previous=reducing["state"].get("valuation"))
        state, _ = finalize(reducing, exit_request, refused, actual, now=at)
        self.assertIn(entry_request, state["risk_control"]["pending"])
        self.assertNotIn(exit_request, state["risk_control"]["pending"])
        with self.assertRaises(PaperConflict):
            replenish(state, now=at)
        with self.assertRaises(PaperConflict):
            self.intent({**reducing, "state": state, "version": reducing["version"]+1}, policy, now=at)

    def test_missing_exit_credits_or_oversized_frame_fail_before_observation(self):
        account, policy = self.account()
        with self.assertRaises(PaperCapacity):
            self.intent(account, policy, frame={"data": "x"*(60*1024)})
        held, policy, _, _, structure = self.held()
        held["state"]["risk_control"]["exit_credits"][structure] = 1
        with self.assertRaises(PaperCapacity):
            self.intent(held, policy, now=NOW+timedelta(seconds=2), action="reduce", structure=structure)


    def test_unknown_missing_or_fabricated_observation_cannot_clear_intent(self):
        account, policy = self.account()
        begun, request, _, frame = self.intent(account, policy)
        actual = observe(begun["state"], frame, now=NOW, binding=binding_of(begun))
        fabricated = copy.deepcopy(actual)
        fabricated["equity"] = "9999"
        future = {**actual, "observed_at": (NOW+timedelta(seconds=1)).isoformat()}
        unknown = copy.deepcopy(actual)
        unknown["risk"]["status"] = "unknown"
        for snapshot in (None, fabricated, future, unknown):
            with self.subTest(snapshot=snapshot), self.assertRaises(PaperConflict):
                finalize(begun, request, {"status": "unknown"}, snapshot, now=NOW)
        self.assertIn(request, begun["state"]["risk_control"]["pending"])


    def test_reducing_intent_cannot_complete_a_buy(self):
        held, policy, params, record, structure = self.held()
        at = NOW+timedelta(seconds=2)
        begun, request, _, frame = self.intent(held, policy, now=at, action="reduce", structure=structure)
        actual = observe(begun["state"], frame, now=at, binding=binding_of(begun), previous=begun["state"].get("valuation"))
        buy = prepare_stage(begun, params, expected_version=begun["version"], trade_evidence=record, frame=frame, now=at)
        self.assertEqual(buy["status"], "pass", buy)
        with self.assertRaises(PaperConflict):
            finalize(begun, request, buy, actual, now=at)
        self.assertIn(request, begun["state"]["risk_control"]["pending"])

    def test_candidate_from_other_frame_cannot_use_captured_actual_reading(self):
        held, policy, params, record, _ = self.held()
        at = NOW+timedelta(seconds=2)
        begun, request, _, frame = self.intent(held, policy, now=at)
        actual = observe(begun["state"], frame, now=at, binding=binding_of(begun), previous=begun["state"].get("valuation"))
        other_frame = frame_fixture(policy, now=at, bid="1.80", ask="1.90")
        candidate = prepare_stage(begun, params, expected_version=begun["version"], trade_evidence=record, frame=other_frame, now=at)
        self.assertEqual(candidate["status"], "pass", candidate)
        with self.assertRaises(PaperConflict):
            finalize(begun, request, candidate, actual, now=at)


if __name__ == "__main__":
    unittest.main()
