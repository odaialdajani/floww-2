"""R6-4 red tests: semantic explainer binding (B05-B07)."""

import sys

sys.path.insert(0, "backend")


def _pkt(**kw):
    from services.solstice_ai_eval import _packet_for
    pkt = _packet_for({"id": "stale_ask",
                       "quality": {"setupEligible": False, "reasonCodes": ["STALE_ASK"]}})
    pkt.update(kw)
    return pkt


def _honest(pkt):
    from services.solstice_evidence import deterministic_fallback
    out = deterministic_fallback(pkt)
    out["observations"] = [{"text": "spot is 500",
                            "evidence_refs": ["fact-spot"],
                            "values": [{"fact_id": "fact-spot", "value": 500.0}]}]
    return out


def test_b05_suffix_numbers_rejected():
    from services.solstice_evidence import validate_explainer_output
    pkt = _pkt()
    out = _honest(pkt)
    out["observations"][0]["text"] = "Spot is 500M here"
    assert validate_explainer_output(out, pkt) != []


def test_b06_promotion_needs_confirmed_state():
    from services.solstice_ai_eval import _packet_for
    from services.solstice_evidence import build_evidence_packet, validate_explainer_output
    pkt = _packet_for({"id": "stale_ask",
                       "quality": {"setupEligible": False, "reasonCodes": ["STALE_ASK"]}})

    def _honest(p):
        from services.solstice_evidence import deterministic_fallback
        out = deterministic_fallback(p)
        out["observations"] = [{"text": "spot is 500",
                                "evidence_refs": ["fact-spot"],
                                "values": [{"fact_id": "fact-spot", "value": 500.0}]}]
        return out

    out = _honest(pkt)
    out["status"] = "Setup confirmed for review"
    # Interaction merely testing (or absent) can never confirm a setup.
    assert validate_explainer_output(out, pkt) != []
    # Even with eligible quality, a testing interaction cannot confirm.
    snap = {"snapshotId": "s1", "queryKey": "q",
            "scope": {"formulaVersion": "gex.v2"},
            "payload": {"spot": 500.0, "exposure_basis": "OI",
                        "metrics": {"walls": [{"wall_id": "w_a", "low": 498, "high": 502}]},
                        "interactions": [{"wall_id": "w_a", "state": "testing"}]},
            "quality": {"setupEligible": True, "reasonCodes": []}}
    pkt2 = build_evidence_packet(snap, wall_id="w_a")
    out2 = _honest(pkt2)
    out2["status"] = "Setup confirmed for review"
    assert validate_explainer_output(out2, pkt2) != []


def test_b07_template_rendering_binds_fields():
    from services.solstice_evidence import render_clause, validate_explainer_output
    pkt = _pkt()
    text = render_clause("spot_state", pkt)
    assert text == "Spot is 500.0 (USD)."
    out = _honest(pkt)
    out["observations"] = [{"text": text, "template": "spot_state",
                            "evidence_refs": ["fact-spot"],
                            "values": [{"fact_id": "fact-spot", "value": 500.0}]}]
    assert validate_explainer_output(out, pkt) == []
    bad = dict(out)
    bad["observations"] = [dict(out["observations"][0], text=text + " extra")]
    assert validate_explainer_output(bad, pkt) != []
