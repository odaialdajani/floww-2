"""R5-E red tests: evidence-bound explanation (G6/R08,R18)."""

import sys

sys.path.insert(0, "backend")


def _pkt():
    from services.solstice_ai_eval import _packet_for
    return _packet_for({"id": "stale_ask",
                        "quality": {"setupEligible": False, "reasonCodes": ["STALE_ASK"]}})


def _honest(pkt):
    from services.solstice_evidence import deterministic_fallback
    out = deterministic_fallback(pkt)
    out["observations"] = [{"text": "spot is 500",
                            "evidence_refs": ["fact-spot"],
                            "values": [{"fact_id": "fact-spot", "value": 500.0}]}]
    return out


def test_r08_prose_numbers_bound_to_facts():
    from services.solstice_evidence import validate_explainer_output
    pkt = _pkt()
    out = _honest(pkt)
    out["observations"][0]["text"] = "Spot is 999999"
    assert validate_explainer_output(out, pkt) != []
    out2 = _honest(pkt)
    out2["headline"] = "Wall breaks toward 123456"
    assert validate_explainer_output(out2, pkt) != []
    assert validate_explainer_output(_honest(pkt), pkt) == []


def test_r08_evidence_carries_selected_wall_context():
    from services.solstice_evidence import build_evidence_packet
    snap = {"snapshotId": "s1", "queryKey": "q",
            "scope": {"formulaVersion": "gex.v2"},
            "payload": {"spot": 500.0, "exposure_basis": "OI",
                        "metrics": {"walls": [{"wall_id": "w_a", "low": 498, "high": 502,
                                               "gross": 1e6, "net": 1e5}]},
                        "interactions": [{"wall_id": "w_a", "state": "testing"}],
                        "scenarios": [{"wall_id": "w_a", "name": "Bounce watch"}],
                        "window_daddex": 250.0},
            "quality": {"setupEligible": False, "reasonCodes": ["STALE_ASK"]}}
    pkt = build_evidence_packet(snap, wall_id="w_a")
    kinds = {f["kind"] for f in pkt["facts"]}
    assert "INTERACTION" in kinds and "SCENARIO" in kinds and "QUALITY" in kinds


def test_r18_study_rejects_reversed_and_rushed_answers():
    import json

    from scripts.solstice_comprehension import expected, score
    with open("backend/tests/solstice/fixtures/comprehension_v1.json") as fh:
        sc = json.load(fh)["scenarios"][0]
    key = expected(sc)
    rev = {"walls": " ".join(str(int(x)) for x in reversed(key["walls"])),
           "level_kind": "OI structure",
           "confirm": "reclaim and hold above the zone; required evidence first",
           "invalidate": "not applicable while waiting for required evidence",
           "blocker": "trade immediately"}
    assert score(sc, rev)["total"] < 5
    assert score(sc, rev)["walls"] is False
