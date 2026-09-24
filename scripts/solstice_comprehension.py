#!/usr/bin/env python3
"""Solstice comprehension harness (T11/T23 ten-second gates, self-administered).

Presents frozen blinded scenarios (no future information) and scores five
interpretation tasks per scenario with direction-aware structured grading:
  1. nearest wall below AND above (ordered pairs: first pair is below,
     second is above; bounds within tolerance; swapped ranges fail)
  2. OI structure vs activity (must say structure/OI, never activity-only)
  3. confirmation condition (direction words must match the scenario side)
  4. invalidation (direction words must match the opposite side)
  5. why setup is withheld / blocker (reason code or WAIT vocabulary;
     action language like "trade immediately" fails as false confidence)

The CLI never prints wall bounds before asking (answers would be coached).
Per-question latency is recorded; hidden answer keys are never shown to
participants (selftest uses the key only as a CI regression gate).

Usage:
    python3 scripts/solstice_comprehension.py --selftest   # CI: answer key scores 100%
    python3 scripts/solstice_comprehension.py             # interactive (~10 min)

Report (JSON) goes to /tmp/solstice_comprehension_report.json — never git.
"""

from __future__ import annotations

import json
import os
import re
import sys

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "backend", "tests",
                       "solstice", "fixtures", "comprehension_v1.json")
NUM_TOL = 0.51


def _nums(text: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*", text or "")]


def _has_all(text: str, words: list[str]) -> bool:
    t = (text or "").lower()
    return all(w in t for w in words)


def expected(sc: dict) -> dict:
    """Deterministic answer key derived from frozen facts only.

    Direction-aware: the scenario side comes from spot vs the nearest walls
    (spot above the lower wall = bounce side; spot below the upper wall =
    rejection side). Confirmation names the hold side; invalidation names the
    adverse side. Swapped sides fail.
    """
    key: dict = {}
    b, a = sc.get("nearest_below"), sc.get("nearest_above")
    inside = sc.get("inside_wall")
    key["below"] = [b["low"], b["high"]] if b else []
    key["above"] = [a["low"], a["high"]] if a else []
    key["inside"] = [inside["low"], inside["high"]] if inside else []
    key["walls"] = key["below"] + key["above"] + key["inside"]
    key["level_kind"] = ["structure", "oi"]
    _q = sc.get("quality") or {}
    blocked = not _q.get("setupEligible", _q.get("setup_eligible", True))
    reasons = _q.get("reasonCodes", _q.get("reason_codes", []))
    # Direction from frozen geometry: spot holds above the lower wall
    # (bounce) and below the upper wall (rejection); spot inside a wall
    # watches the hold inside with acceptance beyond as invalidation.
    if inside and not b and not a:
        key["confirm_side"] = "inside"
        key["invalidate_side"] = "beyond"
    else:
        key["confirm_side"] = "above" if b else "below"
        key["invalidate_side"] = "below" if b else "above"
    if blocked:
        key["confirm"] = ["required", "evidence"]
        key["invalidate"] = ["not", "applicable"]
        key["blocker"] = [r.lower().replace("_", " ") for r in reasons] or ["wait"]
    else:
        key["confirm"] = ["reclaim", "hold"]
        key["invalidate"] = ["acceptance"]
        key["blocker"] = ["trade", "side", "unknown"]
    return key


def _pair_ok(got: list[float], exp: list[float]) -> bool:
    return len(got) >= 2 and len(exp) >= 2 and all(
        any(abs(g - e) <= NUM_TOL for g in got) for e in exp)


def score(sc: dict, answers: dict[str, str]) -> dict:
    key = expected(sc)
    got = _nums(answers.get("walls", ""))
    # Ordered pairs: first pair claims BELOW, second claims ABOVE. Reversed
    # ranges fail even when all four numbers are present.
    if not key["below"] and not key["above"] and not key["inside"]:
        wall_ok = len(got) == 0
    else:
        wall_ok = ((not key["below"] or _pair_ok(got[:2], key["below"]))
                   and (not key["above"] or _pair_ok(got[2:4], key["above"]))
                   and (not key["inside"] or _pair_ok(got[:2], key["inside"])))
    confirm_txt = (answers.get("confirm", "") or "").lower()
    invalidate_txt = (answers.get("invalidate", "") or "").lower()
    r = {
        "walls": wall_ok,
        "level_kind": False,
        "confirm": _has_all(confirm_txt, key["confirm"]) and key["confirm_side"] in confirm_txt,
        "invalidate": _has_all(invalidate_txt, key["invalidate"]) and key["invalidate_side"] in invalidate_txt,
        "blocker": any(w in (answers.get("blocker", "").lower()) for w in key["blocker"]),
    }
    # Q2 must say structure (activity alone is wrong: the frozen level is OI).
    txt = (answers.get("level_kind", "") or "").lower()
    r["level_kind"] = ("structure" in txt or "oi" in txt) and ("only activity" not in txt)
    # Q5 action language ("trade immediately", "trade now") is false
    # confidence, never a blocker answer.
    btxt = (answers.get("blocker", "") or "").lower()
    if "immediately" in btxt or "trade now" in btxt or "buy now" in btxt or "sell now" in btxt:
        r["blocker"] = False
    r["total"] = sum(1 for v in r.values() if v is True)
    return r


QUESTIONS = [
    ("walls", "Q1 nearest wall below AND above (give both bounds, e.g. 754-755 and 757-783): "),
    ("level_kind", "Q2 is this level OI structure or recent activity? "),
    ("confirm", "Q3 what price action would CONFIRM the watch? "),
    ("invalidate", "Q4 what price action INVALIDATES it? "),
    ("blocker", "Q5 why is a setup withheld here (or the main blocker)? "),
]


def run(interactive: bool = True, scripted: dict[str, dict] | None = None) -> dict:
    import time as _time
    scenarios = json.load(open(FIXTURE))["scenarios"]
    report = {"scenarios": [], "total": 0, "possible": 0}
    for sc in scenarios:
        # Never print wall bounds before asking: the participant must locate
        # the walls from the frozen grid, not read them off the prompt.
        print(f"\n=== {sc['id']}  {sc['ticker']} spot {sc['spot']} "
              f"regime {sc['regime']} basis {sc['basis']} ===")
        q = sc.get("quality") or {}
        print(f"  walls: below={'LOADED' if sc.get('nearest_below') else 'none'} "
              f"above={'LOADED' if sc.get('nearest_above') else 'none'}")
        print(f"  quality: eligible={q.get('setupEligible')} reasons={q.get('reasonCodes')}")
        answers: dict[str, str] = {}
        latencies: dict[str, float] = {}
        for key, prompt in QUESTIONS:
            if scripted is not None:
                answers[key] = scripted.get(sc["id"], {}).get(key, "")
                latencies[key] = 0.0
            elif interactive:
                _t0 = _time.time()
                try:
                    answers[key] = input(prompt)
                except EOFError:
                    answers[key] = ""
                latencies[key] = round(_time.time() - _t0, 2)
        s = score(sc, answers)
        print(f"  score {s['total']}/5 :: {s}")
        report["scenarios"].append({"id": sc["id"], "score": s, "answers": answers,
                                    "latency_s": latencies})
        report["total"] += s["total"]
        report["possible"] += 5
    print(f"\nTOTAL {report['total']}/{report['possible']}")
    return report


def selftest() -> int:
    """Feed the answer key through the scorer — must be 100% (CI gate).

    Answers are ordered (below pair first) and direction-correct, mirroring
    what a participant who located the walls would write.
    """
    scenarios = json.load(open(FIXTURE))["scenarios"]
    scripted = {}
    for sc in scenarios:
        key = expected(sc)
        scripted[sc["id"]] = {
            "walls": " ".join(str(int(x)) for x in (key["below"] + key["above"] + key["inside"])),
            "level_kind": "OI structure",
            "confirm": f"reclaim and hold {key['confirm_side']} the zone; required evidence first"
            if "required" in key["confirm"] else f"reclaim and hold {key['confirm_side']} the zone",
            "invalidate": f"not applicable {key['invalidate_side']} while waiting for required evidence"
            if "not" in key["invalidate"] else f"sustained acceptance {key['invalidate_side']} the zone",
            "blocker": " ".join(key["blocker"]),
        }
    report = run(interactive=False, scripted=scripted)
    ok = report["total"] == report["possible"]
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    report = run(interactive=True)
    json.dump(report, open("/tmp/solstice_comprehension_report.json", "w"), indent=1)
    print("report → /tmp/solstice_comprehension_report.json")
