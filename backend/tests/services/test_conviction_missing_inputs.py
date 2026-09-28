"""H3: a missing scorer must not read as neutral evidence.

Repro from the integration audit, measured against `conviction_rank` at
`d905c9d2`:

    ALL-MISSING conviction: 17.5
    components: {'flow': 0.0, 'opportunity': 0.0, 'confluence': 0.5, 'ml': 0.5}
    statuses:   all four 'missing'

`_norm_flow` and `_norm_opp` return 0.0 when their input is None, but
`_norm_conf` returns 0.5 and `_norm_ml` returns 0.5. That asymmetry means a
setup with no evidence at all outranks a setup with real but weak evidence, and
a row whose only data is a fused blob is credited 17.5 of apparently-sourced
conviction.

A missing input is not a neutral observation. It is an absent one, and the
existing `*_status` fields already say so. These tests pin that the fused score
reflects only what was actually supplied.
"""
from __future__ import annotations

from services.conviction_rank import WEIGHTS, rank_many, rank_one

TS = {"snapshot_id": "snap-1", "asof": "2026-09-28T00:00:00+00:00"}


def test_all_missing_scores_zero_not_seventeen():
    """No evidence at all must not produce a non-zero conviction."""
    out = rank_one("SPY", flow=None, opportunity=None, confluence=None, ml=None, **TS)
    ev = out["evidence"]

    assert all(
        ev[k] == "missing"
        for k in ("flow_status", "opportunity_status", "confluence_status", "ml_status")
    ), ev
    assert ev["components"] == {
        "flow": 0.0,
        "opportunity": 0.0,
        "confluence": 0.0,
        "ml": 0.0,
    }, ev["components"]
    assert out["conviction"] == 0.0, out["conviction"]


def test_missing_inputs_cannot_outrank_real_weak_evidence():
    """A blank row must never score above a row with actual evidence."""
    blank = rank_one("SPY", flow=None, opportunity=None, confluence=None, ml=None, **TS)
    weak = rank_one("SPY", flow=8.0, opportunity=1.0, confluence=None, ml=None, **TS)

    assert blank["conviction"] < weak["conviction"], (blank["conviction"], weak["conviction"])


def test_confluence_only_bearish_is_not_penalised_versus_bullish():
    """Symmetric confluence evidence must score identically.

    `_norm_conf` maps [-100, 100] onto [0, 1] via (v + 100) / 200, so a total of
    0 lands on 0.5. That is correct for a signed measure and wrong for a
    magnitude: a confluence reading of exactly 0 means 'no confluence signal',
    not 'half a bullish signal'. Whatever the fix, an equally strong bearish and
    bullish reading must not differ solely because one maps to zero.
    """
    bull = rank_one("SPY", confluence={"total": 40.0}, opportunity=None, flow=None, ml=None, **TS)
    bear = rank_one("SPY", confluence={"total": -40.0}, opportunity=None, flow=None, ml=None, **TS)

    assert bull["conviction"] == bear["conviction"], (bull["conviction"], bear["conviction"])


def test_conviction_blob_is_not_reinterpreted_as_ml():
    """A fused blob must not be re-read as a scorer input.

    `rank_many` inspects the caller's `conviction` dict for scorer-shaped keys
    and forwards whichever it recognises. A blob carrying only `label` is
    matched by the ML branch (`ml.get("label", ...)`), so a fused row silently
    acquires an ml component it never had.
    """
    # `label` is the giveaway: it is an ML-branch key. `score` alone is a
    # legitimate flow key, so the blob is made ml-shaped only.
    blob = {"label": "high"}
    out = rank_many([{"ticker": "SPY", "opportunity": None, "conviction": blob, **TS}])[0]
    ev = out["evidence"]

    # An unrecognised label must not become a silent HOLD.
    assert ev["ml_status"] in ("missing", "invalid"), ev
    assert ev["components"]["ml"] == 0.0, ev["components"]
    assert ev["components"]["flow"] == 0.0, ev["components"]


def test_conviction_blob_with_total_is_not_reinterpreted_as_confluence():
    """Same rule for the `total` key, which the confluence branch matches."""
    blob = {"ticker": "SPY", "total": 73.0, "components": {"flow": 0.5}}
    out = rank_many([{"ticker": "SPY", "opportunity": None, "conviction": blob, **TS}])[0]
    ev = out["evidence"]

    assert ev["confluence_status"] == "missing", ev
    assert ev["components"]["confluence"] == 0.0, ev["components"]


def test_real_scorer_dicts_are_still_unpacked():
    """The fix must not break legitimate scorer-shaped payloads.

    `rank_many` matches on keys present at the TOP level of the `conviction`
    dict, so a scorer payload nests its own scorer key one level down and is
    deliberately not unpacked. This test uses the top-level shape that
    `test_universe_scan_conviction.py` establishes.
    """
    # A raw flow payload and a raw ml payload, each on its own.
    flow_blob = {"conviction": 80.0}
    ml_blob = {"prediction": "BULLISH", "confidence": 0.9}
    rows = rank_many([
        {"ticker": "FLOW", "opportunity": None, "conviction": flow_blob, **TS},
        {"ticker": "ML", "opportunity": None, "conviction": ml_blob, **TS},
    ])
    by_ticker = {r["ticker"]: r for r in rows}

    assert by_ticker["FLOW"]["evidence"]["flow_status"] == "ok", by_ticker["FLOW"]["evidence"]
    assert by_ticker["FLOW"]["evidence"]["components"]["flow"] == 0.8, by_ticker["FLOW"]["evidence"]
    assert by_ticker["ML"]["evidence"]["ml_status"] == "ok", by_ticker["ML"]["evidence"]
    assert by_ticker["ML"]["evidence"]["components"]["ml"] > 0.0, by_ticker["ML"]["evidence"]
    assert all(r["conviction"] > 0.0 for r in rows), [r["conviction"] for r in rows]


def test_direction_is_not_inferred_from_zero_mapping():
    """A DOWN label and an UP label must not collapse to different quality.

    The packet flagged 55.5 vs 90.5 for symmetric setups. The asymmetry comes
    from the ml normalizer, not from direction itself, so this pins that equal
    evidence strength yields equal quality regardless of side.
    """
    up = rank_one("SPY", ml={"prediction": "BULLISH", "confidence": 0.8}, **TS)
    down = rank_one("SPY", ml={"prediction": "BEARISH", "confidence": 0.8}, **TS)

    assert up["conviction"] == down["conviction"], (up["conviction"], down["conviction"])


def test_fused_output_dict_is_never_unpacked_as_a_scorer():
    """A dict of already-fused components must not be re-read as fresh evidence.

    This is the shape `rank_one` returns inside `evidence["components"]`, and
    the shape a caller can accidentally hand back to `rank_many`. Re-fusing it
    is exactly the double-counting defect: a value that was already a fused
    output would be re-normalised and re-weighted as if it were a new
    observation.

    `fused_markers` must be consulted here, not just scorer-shaped keys -- the
    components dict has none of the scorer keys, so a key-only check cannot
    distinguish it.
    """
    fused_components = {"flow": 0.9, "opportunity": 0.8, "confluence": 0.6, "ml": 0.45}
    out = rank_many([
        {"ticker": "X", "opportunity": None, "conviction": fused_components, **TS}
    ])[0]
    ev = out["evidence"]

    assert all(
        ev[k] == "missing"
        for k in ("flow_status", "opportunity_status", "confluence_status", "ml_status")
    ), ev
    assert out["conviction"] == 0.0, out["conviction"]


def test_fused_markers_block_unpacking_even_with_scorer_keys():
    """An already-fused blob carrying scorer keys must still be refused.

    A fused row can legitimately carry `conviction` or `prediction` keys
    alongside its `components`/`tier` markers. The presence of those markers is
    what proves the payload is an output, so it must win over key-shape
    sniffing.
    """
    fused_blob = {
        "conviction": 80.0,
        "prediction": "BULLISH",
        "components": {"flow": 0.9},
        "tier": "HIGH",
    }
    out = rank_many([{"ticker": "X", "opportunity": None, "conviction": fused_blob, **TS}])[0]
    ev = out["evidence"]

    assert ev["flow_status"] == "missing", ev
    assert ev["ml_status"] == "missing", ev
    assert out["conviction"] == 0.0, out["conviction"]


def test_absent_flow_is_not_reported_as_a_measured_zero():
    """A missing alert feed must not look like a conviction reading of 0.

    `_universe_scan_conviction` used to seed `flow = {"conviction": 0}` before
    attempting the DuckDB read, so an unavailable feed and a genuine zero were
    indistinguishable downstream: `_norm_flow` returned 0.0/"ok" either way and
    the row carried `flow_status: "ok"`. Absent evidence has to be None so the
    module reports "missing".
    """
    absent = rank_one("SPY", flow=None, opportunity=None, confluence=None, ml=None, **TS)
    hardcoded_zero = rank_one(
        "SPY", flow={"conviction": 0}, opportunity=None, confluence=None, ml=None, **TS
    )

    assert absent["evidence"]["flow_status"] == "missing", absent["evidence"]
    assert hardcoded_zero["evidence"]["flow_status"] == "ok", hardcoded_zero["evidence"]
    # The route must therefore pass None, not a seeded zero.
    assert absent["evidence"]["flow_status"] != hardcoded_zero["evidence"]["flow_status"]


def test_weights_sum_to_one():
    """Guards the fusion denominator while the normalizers are in flux."""
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, WEIGHTS
