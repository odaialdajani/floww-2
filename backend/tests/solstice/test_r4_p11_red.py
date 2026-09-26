"""P11 red-first tests (capabilities/operations). Each fails on baseline."""

import sys

sys.path.insert(0, "backend")


def test_p11_registry_27_classified():
    from services.public_capability import registry
    reg = registry()
    assert reg["count"] == 27
    for op in reg["operations"]:
        for k in ("op", "docs", "wrapper", "writes", "tests", "entitlement", "observed"):
            assert k in op, op
        assert op["entitlement"] in ("commissioning_required", "verified", "unknown")
        assert op["observed"] in ("not_observed", "mocked_only", "observed")


def test_p11_shared_budget_singleton():
    from services import public_budget as pb1
    from services import public_budget as pb2
    assert hasattr(pb1, "budget")
    assert pb1.budget is pb2.budget


def test_p11_execution_disarmed():
    import pathlib
    # Solstice boundary: explainer/evidence/scout/session/routes-solstice must
    # never reach a broker order method. (routes/public_brokerage.py is a
    # separate authenticated surface, out of Solstice scope — not touched here.)
    scope = [pathlib.Path("routes/solstice.py"),
             pathlib.Path("services/solstice_evidence.py"),
             pathlib.Path("services/solstice_ai_eval.py"),
             pathlib.Path("services/contract_scout.py")]
    hits = [str(p) for p in scope if "place_order" in p.read_text()]
    assert hits == [], hits
    adapter = pathlib.Path("services/public_api_adapter.py").read_text()
    assert "place_order" not in adapter and "place_limit_order" not in adapter
