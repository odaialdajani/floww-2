"""
backend/tests/services/test_heatseeker_semantics.py

Focused semantic regressions for the Task 6 repairs (2026-11-06):

1. Air pockets must not cross an unobserved strike. The expected strike
   spacing comes from the SAME loaded observation, so a missing strike breaks
   a thin run instead of being silently bridged.
2. Air pockets must be measured over GROSS exposure: two large offsetting
   call/put exposures at one strike net to zero, which is not a thin strike.
3. Node lifecycle must count visit EPISODES (distinct timestamps, sustained
   visits once, exit + re-entry again) instead of counting samples as taps.
4. The beach-ball distance is an observable, not a probability: no
   probability-like ``confidence`` label, explicit distance in points/percent.
5. Velocity measures strike migration; same-node exposure change is a
   different quantity and must be reported separately.
6. A UTC day of stored replay rows across different query scopes cannot
   certify one session: group by scope or refuse.

Pure-service level: no DB, no HTTP, no providers.
"""

import sys
from pathlib import Path
from typing import Any

# __file__ = backend/tests/services/test_heatseeker_semantics.py; parents[2] = backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.heatseeker import (  # noqa: E402
    calc_air_pockets,
    calc_node_lifecycle,
    calc_velocity_mode,
    detect_beach_ball,
    group_replay_sessions,
)

# ---------------------------------------------------------------------------
# Fixture helpers (same conventions as test_heatseeker.py)
# ---------------------------------------------------------------------------

def _c(strike: float, ctype: str, gamma: float, oi: float) -> dict[str, Any]:
    return {"strike": strike, "type": ctype, "gamma": gamma, "open_interest": oi}


def _big(spot: float = 100.0) -> list[dict[str, Any]]:
    """One dense anchor strike — gamma/OI chosen so |GEX| dwarfs a thin row."""
    return [_c(spot, "C", 0.05, 1000)]


# ===========================================================================
# 1. Omitted-strike-aware air pockets
# ===========================================================================

class TestAirPocketsOmittedStrike:
    def test_missing_strike_breaks_the_pocket(self):
        """
        Large exposures at 98, 102 and 103; small exposures at 99 and 101;
        NO observation at 100. The loaded ladder is 98, 99, 101, 102, 103 —
        its expected spacing is 1 point. 99 -> 101 spans 2 points, so at
        least one listed strike was not observed and the thin run must break
        there. 99-101 must NOT be reported as one air pocket.
        """
        spot = 100.0
        contracts = [
            _c(98.0, "C", 0.05, 1000),
            _c(99.0, "C", 0.0001, 1),
            _c(101.0, "C", 0.0001, 1),
            _c(102.0, "C", 0.05, 1000),
            _c(103.0, "C", 0.05, 1000),
        ]
        result = calc_air_pockets(spot, contracts, min_gap_pct=0.005)
        pockets = result["air_pockets"]
        # No pocket may span the unobserved strike 100.
        for p in pockets:
            assert p["low"] < 100.0 < p["high"] is False
        assert all(not (p["low"] <= 100.0 <= p["high"]) for p in pockets)
        # The single-strike leftovers (99, 101) are below min span and the
        # bridged run 99-101 is gone entirely.
        assert pockets == []
        # The ladder that produced this answer is disclosed, not assumed.
        assert result["coverage_status"] == "ok"
        assert result["strikes_observed"] == 5
        assert result["expected_step"] == 1.0
        assert result["n_omitted_strikes"] == 1

    def test_contiguous_ladder_keeps_its_pocket(self):
        """
        Same thin strikes, but the ladder is complete: 98..103 with 100
        observed (and thin). A continuously measured thin run is still a
        pocket — the repair must not silence every pocket.
        """
        spot = 100.0
        contracts = [
            _c(98.0, "C", 0.05, 1000),
            _c(99.0, "C", 0.0001, 1),
            _c(100.0, "C", 0.0001, 1),
            _c(101.0, "C", 0.0001, 1),
            _c(102.0, "C", 0.05, 1000),
            _c(103.0, "C", 0.05, 1000),
        ]
        result = calc_air_pockets(spot, contracts, min_gap_pct=0.005)
        assert len(result["air_pockets"]) == 1
        pocket = result["air_pockets"][0]
        assert pocket["low"] == 99.0
        assert pocket["high"] == 101.0
        assert result["n_omitted_strikes"] == 0


class TestAirPocketsGrossExposure:
    def test_call_put_cancellation_is_not_thin(self):
        """
        99, 100 and 101 each carry a large call AND a large put. Their NET
        signed GEX cancels to zero, which the old |net| test read as thin.
        Gross exposure (|call| + |put|) is large at all three strikes, so no
        pocket may be reported. A zero net sum is not a thin strike.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "C", 0.05, 1000),
            _c(96.0, "C", 0.05, 1000),
            _c(97.0, "C", 0.05, 1000),
            _c(98.0, "C", 0.05, 1000),
            # Offsetting large legs — net zero, gross large.
            _c(99.0, "C", 0.05, 5000),
            _c(99.0, "P", 0.05, 5000),
            _c(100.0, "C", 0.05, 5000),
            _c(100.0, "P", 0.05, 5000),
            _c(101.0, "C", 0.05, 5000),
            _c(101.0, "P", 0.05, 5000),
            _c(102.0, "C", 0.05, 1000),
            _c(103.0, "C", 0.05, 1000),
            _c(104.0, "C", 0.05, 1000),
            _c(105.0, "C", 0.05, 1000),
        ]
        result = calc_air_pockets(spot, contracts, min_gap_pct=0.005)
        assert result["air_pockets"] == []
        assert result["basis"] == "gross_exposure"


# ===========================================================================
# 2. Node lifecycle — visit episodes
# ===========================================================================

class TestNodeLifecycleVisitEpisodes:
    def _contracts(self) -> list[dict[str, Any]]:
        return [_c(100.0, "C", 0.05, 5000), _c(105.0, "C", 0.05, 1000)]

    def test_repeated_identical_timestamps_count_one_visit(self):
        """
        Three identical timestamps at the same price are ONE sample and ONE
        visit episode — never three taps and never 'decaying'.
        """
        history = [
            {"timestamp": "2026-05-18T00:00:00Z", "spot": 100.0},
            {"timestamp": "2026-05-18T00:00:00Z", "spot": 100.0},
            {"timestamp": "2026-05-18T00:00:00Z", "spot": 100.0},
        ]
        result = calc_node_lifecycle(100.0, self._contracts(), history)
        node = {n["strike"]: n for n in result["nodes"]}[100.0]
        assert node["taps"] == 1
        assert node["state"] == "tested"
        assert result["history_samples"] == 1
        assert result["duplicate_timestamps_dropped"] == 2

    def test_sustained_visit_is_one_episode(self):
        """
        Five consecutive samples sitting on the strike are one sustained
        visit, not five taps.
        """
        history = [
            {"timestamp": f"2026-05-18T1{h}:00:00Z", "spot": 100.0}
            for h in range(5)
        ]
        result = calc_node_lifecycle(100.0, self._contracts(), history)
        node = {n["strike"]: n for n in result["nodes"]}[100.0]
        assert node["taps"] == 1
        assert node["state"] == "tested"
        assert node["visit_samples"] == 5
        assert result["history_samples"] == 5

    def test_exit_and_re_entry_counts_another_visit(self):
        """
        Visit, exit, re-entry = two episodes. The second visit is a separate
        episode, not a continuation of the first.
        """
        history = [
            {"timestamp": "2026-05-18T01:00:00Z", "spot": 100.0},
            {"timestamp": "2026-05-18T02:00:00Z", "spot": 90.0},   # exit
            {"timestamp": "2026-05-18T03:00:00Z", "spot": 100.05},  # re-entry
        ]
        result = calc_node_lifecycle(100.0, self._contracts(), history)
        node = {n["strike"]: n for n in result["nodes"]}[100.0]
        assert node["taps"] == 2
        assert node["state"] == "delivered"

    def test_untouched_label_requires_adequate_history(self):
        """
        A single distinct sample cannot support an "untouched" claim. Empty
        history stays unknown (existing contract) and one sample is
        insufficient, never 'fresh' — while its measured zero-visit count
        stays visible instead of being erased.
        """
        contracts = self._contracts()
        empty = calc_node_lifecycle(100.0, contracts, [])
        assert empty["history_status"] == "unknown"
        assert empty["reason"] == "HISTORY_UNKNOWN"
        for n in empty["nodes"]:
            assert n["state"] == "unknown"
            assert n["taps"] is None

        one = calc_node_lifecycle(
            100.0, contracts, [{"timestamp": "2026-05-18T00:00:00Z", "spot": 50.0}]
        )
        assert one["history_samples"] == 1
        assert one["min_history_samples"] == 2
        for n in one["nodes"]:
            assert n["state"] == "unknown"
            assert n["reason"] == "HISTORY_INSUFFICIENT"
            assert n["taps"] == 0  # measured zero visits, not a fresh claim
            assert n["tap_probability"] is None

    def test_untracked_timestamps_are_not_invented(self):
        """
        Rows without a usable timestamp are dropped, not guessed, and the
        drop is disclosed rather than silently shrinking the history.
        """
        history = [
            {"timestamp": "not-a-time", "spot": 100.0},
            {"timestamp": None, "spot": 100.0},
            {"spot": 100.0},
            {"timestamp": "2026-05-18T00:00:00Z", "spot": 100.0},
        ]
        result = calc_node_lifecycle(100.0, self._contracts(), history)
        assert result["history_samples"] == 1
        assert result["unusable_rows"] == 3


# ===========================================================================
# 3. Beach ball — distance, not confidence
# ===========================================================================

class TestBeachBallDistance:
    def test_no_confidence_label_and_explicit_distance(self):
        """
        Spot 102 with a single dominant strike at 100: the pattern may be
        active, but the only supported reading is the measured distance —
        in points and in percent. No probability-like ``confidence``.
        """
        contracts = [
            _c(100.0, "C", 0.05, 5000),   # king node
            _c(105.0, "C", 0.05, 200),
        ]
        result = detect_beach_ball(102.0, contracts)
        assert result["active"] is True
        assert result["king_node"] == 100.0
        assert result["spot_distance_points"] == 2.0
        assert result["spot_distance_pct"] == 0.02
        assert result["direction"] == "above"
        assert "confidence" not in result
        assert "tap_probability" not in result

    def test_inactive_payloads_carry_no_confidence_either(self):
        """The inactive/degenerate payloads must not smuggle the label back."""
        for res in (
            detect_beach_ball(0.0, []),
            detect_beach_ball(100.0, []),
            detect_beach_ball(float("nan"), []),
        ):
            assert res["active"] is False
            assert "confidence" not in res


# ===========================================================================
# 4. Velocity — migration separated from exposure change
# ===========================================================================

class TestVelocityMigration:
    def _history(self, with_gex: bool) -> list[dict[str, Any]]:
        rows = []
        for i, kn in enumerate((100.0, 101.0, 102.0)):
            row = {
                "timestamp": f"2026-05-18T00:{i * 5:02d}:00Z",
                "king_node_strike": kn,
                "spot": 101.0,
            }
            if with_gex:
                row["king_node_gex"] = 1e9 * (i + 1)
            rows.append(row)
        return rows

    def test_velocity_is_labelled_strike_migration(self):
        """The measured quantity is named: strike migration in points/minute."""
        result = calc_velocity_mode(self._history(with_gex=False))
        assert result["mode"] in ("active", "urgent", "calm")
        assert result["quantity"] == "strike_migration"
        assert result["unit"] == "points_per_min"
        # Same-node exposure change was NOT supplied and must not be invented.
        assert result["exposure_change"]["measured"] is False
        assert result["exposure_change"]["reason"] == "EXPOSURE_HISTORY_NOT_SUPPLIED"

    def test_exposure_change_is_reported_separately_when_supplied(self):
        """
        An identified node that stays at the same strike can have its own
        dollar exposure change independently of its zero migration rate.
        """
        history = self._history(with_gex=True)
        for row in history:
            row["king_node_strike"] = 100.0
        result = calc_velocity_mode(history)
        assert result["velocity_strikes_per_min"] == 0
        assert result["exposure_change"]["measured"] is True
        assert result["exposure_change"]["unit"] == "dollars_per_min"
        # (3e9 - 1e9) dollars over the 10-minute window.
        assert result["exposure_change"]["value"] == 2e8
        # Migration and exposure change stay different numbers.
        assert result["exposure_change"]["value"] != result["velocity_strikes_per_min"]

    def test_velocity_unknown_states_are_preserved(self):
        """Insufficient/invalid history keeps the unknown contract."""
        for hist in ([], [{"timestamp": "2026-05-18T00:00:00Z", "king_node_strike": 100.0}]):
            res = calc_velocity_mode(hist)
            assert res["mode"] == "unknown"
            assert res["velocity_strikes_per_min"] is None


# ===========================================================================
# 5. Replay session manifest — scope grouping
# ===========================================================================

class TestReplaySessionScopes:
    def _row(self, asof: str, scope: str | None, snap: str) -> dict[str, Any]:        return {"asof": asof, "query_key": scope, "snapshot_id": snap,
                "n_contracts": 10}

    def test_one_scope_certifies_one_session(self):
        rows = [
            self._row("2026-11-06T14:30:00Z", "q=4exp", "s1"),
            self._row("2026-11-06T14:35:00Z", "q=4exp", "s2"),
            # A 10-minute hole against a 300s cadence is an explicit gap.
            self._row("2026-11-06T14:45:00Z", "q=4exp", "s3"),
        ]
        out = group_replay_sessions(rows, expected_cadence_s=300.0,
                                    day="2026-11-06", ticker="SPY")
        assert out["status"] == "ok"
        assert out["n_scopes"] == 1
        assert out["n_snapshots"] == 3
        session = out["sessions"][0]
        assert session["scope"] == "q=4exp"
        assert session["n_snapshots"] == 3
        assert session["gaps"] == [{"from": "2026-11-06T14:35:00Z",
                                    "to": "2026-11-06T14:45:00Z",
                                    "gap_s": 600.0, "missing_beats": 1}]

    def test_two_scopes_on_one_day_are_never_certified_as_one_session(self):
        """
        Two query scopes, one ticker, one UTC day. A single row list across
        them cannot certify a market session: the day is grouped per scope
        and the certification is refused explicitly.
        """
        rows = [
            self._row("2026-11-06T14:30:00Z", "q=4exp", "s1"),
            self._row("2026-11-06T14:35:00Z", "q=12exp", "s2"),
            self._row("2026-11-06T14:40:00Z", "q=4exp", "s3"),
            self._row("2026-11-06T14:45:00Z", "q=12exp", "s4"),
        ]
        out = group_replay_sessions(rows, expected_cadence_s=300.0,
                                    day="2026-11-06", ticker="SPY")
        assert out["status"] == "refused"
        assert out["reason"] == "MIXED_QUERY_SCOPES"
        assert out["n_scopes"] == 2
        assert out["n_snapshots"] == 4
        scopes = {s["scope"]: s for s in out["sessions"]}
        assert set(scopes) == {"q=4exp", "q=12exp"}
        assert scopes["q=4exp"]["n_snapshots"] == 2
        assert scopes["q=12exp"]["n_snapshots"] == 2
        # Each scope keeps its OWN gap accounting — never a merged session.
        # Inside q=4exp the 14:30 -> 14:40 interval is that scope's own gap;
        # the rows of the other scope are never bridged into it.
        four_exp = scopes["q=4exp"]
        twelve_exp = scopes["q=12exp"]
        assert [g["from"] for g in four_exp["gaps"]] == ["2026-11-06T14:30:00Z"]
        assert [g["to"] for g in four_exp["gaps"]] == ["2026-11-06T14:40:00Z"]
        assert [g["from"] for g in twelve_exp["gaps"]] == ["2026-11-06T14:35:00Z"]
        assert [g["to"] for g in twelve_exp["gaps"]] == ["2026-11-06T14:45:00Z"]
        assert [s["asof"] for s in four_exp["snapshots"]] == [
            "2026-11-06T14:30:00Z", "2026-11-06T14:40:00Z",
        ]
        assert "cannot certify" in out["note"]

    def test_missing_scope_is_disclosed_not_dropped(self):
        """Rows with no scope land in a disclosed 'unknown' bucket."""
        rows = [
            self._row("2026-11-06T14:30:00Z", None, "s1"),
            self._row("2026-11-06T14:35:00Z", "", "s2"),
        ]
        out = group_replay_sessions(rows, day="2026-11-06", ticker="SPY")
        assert out["status"] == "ok"
        assert out["n_scopes"] == 1
        assert out["sessions"][0]["scope"] == "unknown"
        assert out["gap_coverage"] == "unknown"
