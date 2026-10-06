"""A missing multiplier must not be silently replaced by 100.0.

`wall_desk_snapshot.project_window` guards the same loop for a missing gamma
and a missing delta -- both `continue`. A missing `multiplier` was instead
defaulted to 100.0 and multiplied into the result, so a contract with no
multiplier contributed a full-magnitude number that nothing downstream
reported as unknown. Because `0.0` is falsy, a *measured* zero multiplier
was also replaced by 100.0, making zero and absent indistinguishable.

S3 contract (Spark): an explicitly invalid multiplier (None, 0.0, negative)
is skipped via domain.exposure_metrics.resolve_multiplier, and a window with
no comparable observations is UNAVAILABLE (None sums + reason), never an
all-zero "measured" window (R10-07). Only a wholly absent multiplier key on
a standard contract takes the documented DEFAULT_STANDARD provenance.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.wall_desk_snapshot import project_window  # noqa: E402


def _obs(osi: str, volume: float, **overrides) -> dict:
    contract = {
        "osi": osi,
        "strike": 100.0,
        "type": "call",
        "gamma": 0.01,
        "delta": 0.5,
        "multiplier": 100.0,
        "volume": volume,
    }
    contract.update(overrides)
    return {"ticker": "SPY", "spot": 100.0, "contracts": [contract]}


FIRST = _obs("c1", volume=5)


def _window(second: dict) -> dict:
    return project_window(FIRST, second)


def _net(second: dict):
    return _window(second).get("window_net")


def test_present_multiplier_is_the_baseline():
    assert _net(_obs("c1", volume=8)) == 150.0


def test_measured_zero_multiplier_stays_zero():
    """A measured 0.0 is skipped: no magnitude, and no zero-fill masquerade."""
    w = _window(_obs("c1", volume=8, multiplier=0.0))
    assert w["window_net"] is None
    assert w["status"] == "unavailable"
    assert w["reason"] == "NO_COMPARABLE_OBSERVATIONS"


def test_missing_multiplier_is_skipped_like_missing_gamma():
    """Absent multiplier must be treated the same way a missing gamma is."""
    w = _window(_obs("c1", volume=8, multiplier=None))
    assert w["window_net"] is None, (
        f"a contract with no multiplier contributed {w['window_net']}; "
        "an absent value must not enter the arithmetic"
    )
    assert w["status"] == "unavailable"
    assert _window(_obs("c1", volume=8, gamma=None))["window_net"] is None, (
        "missing multiplier and missing gamma must be handled identically"
    )


def test_zero_measured_multiplier_is_distinguishable_from_absent():
    """Explicit invalid is unavailable; only a real 100.0 measures 150.0."""
    measured_zero = _net(_obs("c1", volume=8, multiplier=0.0))
    absent = _net(_obs("c1", volume=8, multiplier=None))
    real_default = _net(_obs("c1", volume=8))
    assert real_default == 150.0
    assert absent is None and measured_zero is None, (
        f"absent={absent} measured_zero={measured_zero} real={real_default}"
    )


def test_negative_multiplier_is_rejected_not_accumulated():
    """Guards the `<= 0` half of the fix.

    A 0.0 multiplier cannot distinguish the guards on its own: multiplying by
    zero contributes zero to the running sums either way, so a mutant that
    drops the `mult <= 0` half still produces 0.0. A negative multiplier is
    observable -- without the guard it contributes a negative term and
    inverts the net.
    """
    w = _window(_obs("c1", volume=8, multiplier=-100.0))
    assert w["window_net"] is None, (
        f"a contract with a negative multiplier contributed {w['window_net']}; "
        "a non-positive multiplier must be skipped, not accumulated"
    )
    assert w["status"] == "unavailable"
    assert _window(_obs("c1", volume=8, gamma=None))["status"] == "unavailable", (
        "a negative multiplier must be handled exactly like a missing gamma"
    )
