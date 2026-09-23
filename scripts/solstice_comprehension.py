#!/usr/bin/env python3
"""Solstice comprehension harness (T11/T23 ten-second gates, self-administered).

Presents frozen blinded scenarios (no future information) and scores five
interpretation tasks per scenario:
  1. nearest wall above + below (bounds within tolerance)
  2. OI structure vs activity (keyword)
  3. confirmation condition (keywords)
  4. invalidation (keywords)
  5. why setup is withheld / blocker (reason code or WAIT vocabulary)

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
    """Deterministic answer key derived from frozen facts only."""
    key: dict = {}
    b, a = sc.get("nearest_below"), sc.get("nearest_above")
    key["walls"] = [b["low"], b["high"]] if b else []
    key["walls"] += [a["low"], a["high"]] if a else []
    key["level_kind"] = ["structure", "oi"]
    blocked = not (sc.get("quality") or {}).get("setupEligible", True)
    reasons = (sc.get("quality") or {}).get("reasonCodes", [])
    if blocked:
        key["confirm"] = ["required", "evidence"]
        key["invalidate"] = ["not", "applicable"]
        key["blocker"] = [r.lower().replace("_", " ") for r in reasons] or ["wait"]
    else:
        key["confirm"] = ["reclaim", "hold"]
        key["invalidate"] = ["acceptance"]
        key["blocker"] = ["trade", "side", "unknown"]
    return key


def score(sc: dict, answers: dict[str, str]) -> dict:
    key = expected(sc)
    got = _nums(answers.get("walls", ""))
    wall_ok = all(any(abs(g - e) <= NUM_TOL for g in got) for e in key["walls"]) if key["walls"] else True
    r = {
        "walls": wall_ok,
        "level_kind": _has_all(answers.get("level_kind", ""), key["level_kind"]) or
                      ("activity" in (answers.get("level_kind", "").lower()) and False),
        "confirm": _has_all(answers.get("confirm", ""), key["confirm"]),
        "invalidate": _has_all(answers.get("invalidate", ""), key["invalidate"]),
        "blocker": any(w in (answers.get("blocker", "").lower()) for w in key["blocker"]),
    }
    # Q2 must say structure (activity alone is wrong: the frozen level is OI).
    txt = (answers.get("level_kind", "") or "").lower()
    r["level_kind"] = ("structure" in txt or "oi" in txt) and ("only activity" not in txt)
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
    scenarios = json.load(open(FIXTURE))["scenarios"]
    report = {"scenarios": [], "total": 0, "possible": 0}
    for sc in scenarios:
        print(f"\n=== {sc['id']}  {sc['ticker']} spot {sc['spot']} "
              f"regime {sc['regime']} basis {sc['basis']} ===")
        b, a = sc.get("nearest_below"), sc.get("nearest_above")
        if b:
            print(f"  wall below: zone [{b['low']}, {b['high']}] gross {b['gross']:.1f} net {b['net']:.1f}")
        if a:
            print(f"  wall above: zone [{a['low']}, {a['high']}] gross {a['gross']:.1f} net {a['net']:.1f}")
        q = sc.get("quality") or {}
        print(f"  quality: eligible={q.get('setupEligible')} reasons={q.get('reasonCodes')}")
        answers: dict[str, str] = {}
        for key, prompt in QUESTIONS:
            if scripted is not None:
                answers[key] = scripted.get(sc["id"], {}).get(key, "")
            elif interactive:
                try:
                    answers[key] = input(prompt)
                except EOFError:
                    answers[key] = ""
        s = score(sc, answers)
        print(f"  score {s['total']}/5 :: {s}")
        report["scenarios"].append({"id": sc["id"], "score": s, "answers": answers})
        report["total"] += s["total"]
        report["possible"] += 5
    print(f"\nTOTAL {report['total']}/{report['possible']}")
    return report


def selftest() -> int:
    """Feed the answer key through the scorer — must be 100% (CI gate)."""
    scenarios = json.load(open(FIXTURE))["scenarios"]
    scripted = {}
    for sc in scenarios:
        key = expected(sc)
        scripted[sc["id"]] = {
            "walls": " ".join(str(int(x)) for x in key["walls"]),
            "level_kind": "OI structure",
            "confirm": "reclaim and hold above the zone; required evidence first"
            if "required" in key["confirm"] else "reclaim and hold above the zone",
            "invalidate": "not applicable while waiting for required evidence"
            if "not" in key["invalidate"] else "sustained acceptance above the zone",
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
