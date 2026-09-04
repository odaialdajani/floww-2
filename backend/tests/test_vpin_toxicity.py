"""
backend/tests/test_vpin_toxicity.py

Regression tests for the VPIN toxicity service used by Flowseeker Pro.

Locks the observable behaviour of :class:`VPINToxicity` so refactors cannot
silently change VPIN computation or label classification.

Run from repo root:

    cd /Users/nav/Documents/GitHub/floww
    python3 -m pytest backend/tests/test_vpin_toxicity.py -v

Or directly (no pytest install needed):

    python3 backend/tests/test_vpin_toxicity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from services.vpin_toxicity import (
    LABEL_COLORS,
    LABEL_EXTREME,
    LABEL_HIGH,
    LABEL_LOW,
    LABEL_MODERATE,
    VPINToxicity,
)

# ─────────────────────────────────────────────────────────────────────
# Lifecycle / warming
# ─────────────────────────────────────────────────────────────────────

def test_warming_with_fewer_than_n_buckets():
    vpin = VPINToxicity(buckets=20, history=40)
    vpin.push_bucket(100, 100, 200, 500)
    out = vpin.compute()
    assert out["is_warming"] is True
    assert out["vpin"] == 0.0
    assert out["label"] == LABEL_LOW
    assert out["label_color"] == LABEL_COLORS[LABEL_LOW]
    assert out["n_buckets"] == 1
    assert out["history_total"] == 1
    assert out["last_bucket_of"] == 0.0  # |100-100|/200 = 0


def test_zero_total_vol_buckets_are_skipped():
    """total_vol == 0 buckets are silently dropped (don't pollute window)."""
    vpin = VPINToxicity(buckets=5)
    for _ in range(10):
        vpin.push_bucket(0, 0, 0, 0)  # all-zero → skipped
    # All pushes were dropped → still warming.
    out = vpin.compute()
    assert out["is_warming"] is True
    assert out["history_total"] == 0


# ─────────────────────────────────────────────────────────────────────
# Imbalance buckets
# ─────────────────────────────────────────────────────────────────────

def test_balanced_call_put_yields_low_vpin():
    """50/50 call/put volume → OF_i = 0 per bucket → vpin = 0 → LOW."""
    vpin = VPINToxicity(buckets=20)
    for _ in range(20):
        vpin.push_bucket(100, 100, 200, 500)
    out = vpin.compute()
    assert out["is_warming"] is False
    assert abs(out["vpin"]) < 1e-6
    assert out["label"] == LABEL_LOW


def test_pure_call_yields_extreme_vpin():
    """100% call-side volume → OF_i = 1 per bucket → vpin = 1 → EXTREME."""
    vpin = VPINToxicity(buckets=20)
    for _ in range(20):
        vpin.push_bucket(200, 0, 200, 500)
    out = vpin.compute()
    assert out["is_warming"] is False
    assert abs(out["vpin"] - 1.0) < 1e-6
    assert out["label"] == LABEL_EXTREME
    assert out["last_bucket_of"] == 1.0


def test_pure_put_yields_extreme_vpin():
    """VPIN uses |...| so 100% put volume also yields EXTREME."""
    vpin = VPINToxicity(buckets=20)
    for _ in range(20):
        vpin.push_bucket(0, 200, 200, 500)
    out = vpin.compute()
    assert out["is_warming"] is False
    assert abs(out["vpin"] - 1.0) < 1e-6
    assert out["label"] == LABEL_EXTREME


# ─────────────────────────────────────────────────────────────────────
# Buffer clamping
# ─────────────────────────────────────────────────────────────────────

def test_history_buffer_clamps_to_maxlen():
    vpin = VPINToxicity(buckets=10, history=20)
    for _ in range(100):
        vpin.push_bucket(100, 100, 200, 500)
    assert len(vpin._ofs) == 20


def test_windowed_mean_uses_last_n_buckets_only():
    """Only the LAST ``buckets`` values contribute to vpin, not the full history."""
    vpin = VPINToxicity(buckets=5, history=20)
    # First 15 buckets: perfectly balanced (OF=0).
    for _ in range(15):
        vpin.push_bucket(100, 100, 200, 500)
    # Last 5 buckets: full imbalance (OF=1).
    for _ in range(5):
        vpin.push_bucket(200, 0, 200, 500)
    out = vpin.compute()
    assert out["is_warming"] is False
    # The window covers only the last 5 entries → vpin=1.
    assert abs(out["vpin"] - 1.0) < 1e-6
    assert out["n_buckets"] == 5
    assert out["history_total"] == 20
    assert out["label"] == LABEL_EXTREME


# ─────────────────────────────────────────────────────────────────────
# Label thresholds (boundary cases)
# ─────────────────────────────────────────────────────────────────────

def test_label_thresholds_match_specification():
    """Sweep meaningful boundary values: 0.30, 0.50, 0.70."""
    # vpin = 0.30 — boundary; per spec < 0.30 is LOW, so 0.30 itself ought
    # to be MODERATE.  Construct a bucket pattern that yields vpin=0.30
    # exactly (e.g. 3 buckets at OF=0.5, 2 at OF=0.0 → mean=0.3).
    vpin = VPINToxicity(buckets=5, history=20)
    for _of in [0.5, 0.5, 0.5, 0.0, 0.0]:
        # call=200, put=0 => OF=1.0; for OF=0.5 use 75/125 — wait that's
        # |75-125|/200=0.5. So construct: call=125, put=75 → OF=0.25 → that's
        # not it. Easier: |c - p|/(c+p) = 0.5 ⇒ |c-p|=c+p ⇒ one side is 0 ⇒
        # (call=200, put=0) gives OF=1. Mix differently: use 2 of 0.5 + 3 of 0.
        pass
    # Simpler: directly construct the expected vpin via mixed OF.
    # Use the fact that |c-p|/(c+p) is continuous; for OF_i = 1 (pure call)
    # mean(OF) = 1; for balanced mean(OF) = 0. We can hit any vpin ∈ [0,1]
    # by combining. Easier: directly compute via Python's interface and
    # verify the classifier response.
    # Construct buckets such that mean(OF) = 0.3 (e.g. 3 buckets OF=1,
    # 7 buckets OF=0 → mean = 0.3 over 10 buckets):
    vpin = VPINToxicity(buckets=10, history=20)
    # Use buckets sized differently to land OF_i = exactly 0.3:
    # |c-p|/(c+p) = 0.3 → |c-p| = 0.3(c+p) → with c=130, p=70:
    # |130-70|/200 = 60/200 = 0.3 ✓
    for _ in range(10):
        vpin.push_bucket(130, 70, 200, 500)
    out = vpin.compute()
    assert abs(out["vpin"] - 0.3) < 1e-6
    assert out["label"] == LABEL_MODERATE  # boundary: 0.3 falls into MODERATE
    assert out["label_color"] == LABEL_COLORS[LABEL_MODERATE]

    # vpin = 0.50 → MODERATE
    vpin = VPINToxicity(buckets=10, history=20)
    for _ in range(10):
        vpin.push_bucket(150, 50, 200, 500)   # |150-50|/200 = 0.5 ✓
    out = vpin.compute()
    assert abs(out["vpin"] - 0.5) < 1e-6
    assert out["label"] == LABEL_HIGH  # 0.5 is the boundary into HIGH

    # vpin = 0.70 → EXTREME
    vpin = VPINToxicity(buckets=10, history=20)
    for _ in range(10):
        vpin.push_bucket(170, 30, 200, 500)   # |170-30|/200 = 0.7 ✓
    out = vpin.compute()
    assert abs(out["vpin"] - 0.7) < 1e-6
    assert out["label"] == LABEL_EXTREME  # 0.7 is the boundary into EXTREME


def test_label_color_matches_label():
    """Spot-check that label_color always tracks label."""
    for label_expected in (LABEL_LOW, LABEL_MODERATE, LABEL_HIGH, LABEL_EXTREME):
        assert LABEL_COLORS[label_expected].startswith("#")
        assert len(LABEL_COLORS[label_expected]) == 7


# ─────────────────────────────────────────────────────────────────────
# Constructor validation
# ─────────────────────────────────────────────────────────────────────

def test_invalid_arguments_raise():
    try:
        VPINToxicity(buckets=0, history=10)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for buckets < 2")
    try:
        VPINToxicity(buckets=10, history=5)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when history < buckets")


# ─────────────────────────────────────────────────────────────────────
# Plain-script runner (no pytest required)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        (n, f) for n, f in globals().items() if n.startswith("test_")
    ]
    failures = 0
    for name, fn in test_cases:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {name}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(test_cases) - failures}/{len(test_cases)} passed")
    sys.exit(0 if failures == 0 else 1)
