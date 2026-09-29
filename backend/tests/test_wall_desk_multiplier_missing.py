"""A missing multiplier must not be silently replaced by 100.0.

`wall_desk_snapshot.project_window` guards the same loop for a missing gamma
and a missing delta -- both `continue`. A missing `multiplier` was instead
defaulted to 100.0 and multiplied into the result, so a contract with no
multiplier contributed a full-magnitude number that nothing downstream
reported as unknown. Because `0.0` is falsy, a *measured* zero multiplier
was also replaced by 100.0, making zero and absent indistinguishable.

`gex_core._resolve_mult` is the reference shape: default, then validate
finite and positive, then fall back. The measured-zero case must survive as
0.0, not become 100.0.
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


def _net(second: dict) -> float:
    return project_window(FIRST, second).get("window_net")


def test_present_multiplier_is_the_baseline():
    assert _net(_obs("c1", volume=8)) == 150.0


def test_measured_zero_multiplier_stays_zero():
    """A measured 0.0 is a measurement, not a missing value."""
    assert _net(_obs("c1", volume=8, multiplier=0.0)) == 0.0


def test_missing_multiplier_is_skipped_like_missing_gamma():
    """Absent multiplier must be treated the same way a missing gamma is."""
    missing_mult = _net(_obs("c1", volume=8, multiplier=None))
    missing_gamma = _net(_obs("c1", volume=8, gamma=None))
    assert missing_mult == 0.0, (
        f"a contract with no multiplier contributed {missing_mult}; "
        "an absent value must not enter the arithmetic"
    )
    assert missing_mult == missing_gamma, (
        "missing multiplier and missing gamma must be handled identically"
    )


def test_zero_measured_multiplier_is_distinguishable_from_absent():
    """Both are unusable, but they must not be conflated with a real 100.0."""
    measured_zero = _net(_obs("c1", volume=8, multiplier=0.0))
    absent = _net(_obs("c1", volume=8, multiplier=None))
    real_default = _net(_obs("c1", volume=8))
    assert real_default == 150.0
    assert absent == measured_zero == 0.0, (
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
    negative = _net(_obs("c1", volume=8, multiplier=-100.0))
    assert negative == 0.0, (
        f"a contract with a negative multiplier contributed {negative}; "
        "a non-positive multiplier must be skipped, not accumulated"
    )
    assert negative == _net(_obs("c1", volume=8, gamma=None)), (
        "a negative multiplier must be handled exactly like a missing gamma"
    )
