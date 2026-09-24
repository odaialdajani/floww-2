"""P08 red-first tests (R4-03/04). Each fails on baseline behavior."""

import sys

sys.path.insert(0, "backend")


def _pkt():
    from services.solstice_ai_eval import _packet_for
    return _packet_for({"id": "stale_ask",
                        "quality": {"setupEligible": False, "reasonCodes": ["STALE_ASK"]}})


def test_r4_04_tool_attempt_rejected():
    from services.solstice_evidence import validate_explainer_output
    pkt = _pkt()
    out = {"snapshot_id": pkt["snapshot_id"], "query_id": pkt["query_id"],
           "status": "Wait", "headline": "wait", "observations": [], "hypotheses": [],
           "conflicts": [], "next_condition": "x", "invalidation": "y",
           "candidate_refs": [], "evidence_refs": ["fact-spot"],
           "tool_calls": [{"tool": "place_order"}]}
    assert validate_explainer_output(out, pkt) != []


def test_r4_04_injection_promotion_blocked():
    from services.solstice_ai_eval import run_corpus
    from services.solstice_evidence import deterministic_fallback

    def promoter(p):
        out = deterministic_fallback(p)
        out["status"] = "Setup confirmed for review"
        return out

    rep = run_corpus(promoter)
    assert rep["passed"] < rep["n"]


def test_r4_04_outage_is_fallback_not_model():
    from services.solstice_ai_eval import run_corpus
    rep = run_corpus(None)
    assert rep["model_evaluated"] is False
    assert all(r["mode"] == "fallback" for r in rep["results"])


def test_r4_03_walls_scope_aligned():
    import inspect

    from routes import solstice as rs
    sig = inspect.signature(rs.walls)
    params = set(sig.parameters)
    assert {"mode", "dte", "scalp"} <= params
    src = inspect.getsource(rs.walls)
    assert "scope" in src and "query" in src.lower()
