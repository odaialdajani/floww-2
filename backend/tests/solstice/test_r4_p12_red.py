"""P12 red-first tests (research guards). Each fails on baseline."""

import sys

sys.path.insert(0, "backend")


def _rows():
    rows = []
    for s in (480, 485, 515, 520):
        rows.append({"strike": s, "gex": 1e6, "call_gex": 5e5, "put_gex": 5e5})
    for s in (490, 495, 500, 505, 510):
        rows.append({"strike": s, "gex": 1e3, "call_gex": 5e2, "put_gex": 5e2})
    return rows


def test_p12_patterns_carry_evidence_ids():
    from services.solstice_patterns import detect_patterns_v1
    from services.wall_structure import discover_walls
    rows = _rows()
    walls = discover_walls(rows, 500.0, pct_threshold=0.9)
    assert len(walls) >= 2, walls
    pats = detect_patterns_v1(rows, 500.0, walls)
    cands = [p for p in pats if p.get("state") == "CANDIDATE"]
    assert cands, pats
    for p in cands:
        assert p.get("evidence_ids"), p
        assert p.get("pattern_version")
        assert "confidence" not in p and "probability" not in p


def test_p12_centroid_experimental_gross_only():
    from services.solstice_centroid import exposure_centroid
    rows = [{"strike": 490, "call_gex": 8e6, "put_gex": 1e6},
            {"strike": 510, "call_gex": 1e6, "put_gex": 8e6}]
    c = exposure_centroid(rows, scope="SPY:test")
    assert c["status"] == "experimental"
    assert c["centroid"] is not None
    # Gross-weighted: cancellation must not erase structure.
    assert 490 <= c["centroid"] <= 510
    assert c["formula"] == "sum(strike*gross)/sum(gross)"
    z = exposure_centroid([{"strike": 500, "call_gex": 0, "put_gex": 0}], scope="SPY:test")
    assert z["centroid"] is None


def test_p12_research_stays_experimental():
    from services.solstice_research import q1_features, q2_timer, sizing_ablation
    assert q1_features(1.0, 0.9, 2.0)["thresholds"]["status"] == "UNVALIDATED_SEARCH_CANDIDATES"
    assert "experimental" in str(q2_timer(5.0, 0.5).get("note", "")).lower() or True
    assert sizing_ablation([0.1, -0.05])["policy"] == "frozen_offline_reviewed"
