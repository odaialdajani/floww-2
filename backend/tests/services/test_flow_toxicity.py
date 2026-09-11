"""A3: bar-VPIN toxicity + O/S venue + gate/slippage helpers (Agent A).

Pure functions on injected bars-lists (C13 shapes [{t,o,h,l,c,v}]) — no
network. Bar-data adaptations of the papers are documented per function,
never silent.
"""

from services.flow_toxicity import (
    bucket_imbalance,
    os_ratio,
    projected_slippage_bp,
    toxicity_gate,
    vpin_from_bars,
)


def _bars(closes, vol=1000.0):
    return [{"t": f"2026-09-04T10:{i:02d}:00", "o": c, "h": c, "l": c, "c": c, "v": vol}
            for i, c in enumerate(closes)]


def test_vpin_one_sided_tape_is_maximal():
    bars = [{"t": f"2026-09-04T10:{i:02d}:00", "o": 100.0 + i * 0.5 - 0.5,
             "h": 101.0 + i, "l": 99.0, "c": 100.0 + i * 0.5, "v": 1000.0}
            for i in range(20)]  # every bar an uptick
    out = vpin_from_bars(bars, n_buckets=5)
    assert out["vpin"] == 1.0
    assert out["buckets_filled"] == 5


def test_vpin_balanced_tape_is_quiet():
    bars = _bars([100.0 + (0.5 if i % 2 else -0.5) for i in range(20)])
    out = vpin_from_bars(bars, n_buckets=5)
    assert out["vpin"] is not None and out["vpin"] < 0.3


def test_vpin_thin_history_is_none_not_zero():
    assert vpin_from_bars(_bars([100.0, 101.0]), n_buckets=50)["vpin"] is None
    assert vpin_from_bars([])["vpin"] is None


def test_bucket_imbalance_sign():
    assert bucket_imbalance(800.0, 200.0) == 0.6
    assert bucket_imbalance(0.0, 0.0) is None


def test_os_ratio_venue_share():
    # 5k contracts = 500k shares vs 2M share volume -> 0.25
    assert os_ratio(5000, 2_000_000) == 0.25
    assert os_ratio(0, 2_000_000) == 0.0
    assert os_ratio(5000, 0) is None


def test_toxicity_gate_requires_threshold():
    assert toxicity_gate(0.85, threshold=0.7) == ("BLOCK", "vpin 0.85 >= 0.70")
    assert toxicity_gate(0.40, threshold=0.7) == ("ALLOW", "vpin 0.40 < 0.70")
    assert toxicity_gate(None, threshold=0.7)[0] == "ALLOW"  # unknown != toxic


def test_projected_slippage_bp_units():
    # lambda in return-per-$: 1e-6 * $1M * 1e4 = 10000bp. Math pin.
    assert projected_slippage_bp(1e-6, 1_000_000) == 10000.0
    assert projected_slippage_bp(None, 1_000_000) is None
    assert projected_slippage_bp(1e-6, 0) == 0.0
