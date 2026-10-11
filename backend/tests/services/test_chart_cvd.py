"""BVC-estimated CVD from OHLCV+volume (Easley/Lopez de Prado/O'Hara 2012).

RED-first suite per BVC_CVD_IMPLEMENTATION_SPEC.md section 6.

Honesty amendment (documented, not silent): the spec's section 6 contains two
tests that cannot both hold. `test_constant_price_flat_delta` (5 flat bars,
window=20) expects delta=0 after the first bar, while `test_sigma_zero_gap`
(5 flat bars, window=10) expects gaps for all bars. The inputs differ only in
window size, and a LARGER window yielding values while a SMALLER window yields
gaps matches no rolling-std rule in either direction. Resolution, favouring
the section 4 sanity table ("constant price -> delta 0, CVD flat") plus the
majority of the spec's own tests:

- sigma uses trailing available session history (up to W returns);
- delta == 0 (no price move) -> balanced split, delta 0, whatever sigma is;
- sigma == 0 with a real move -> maximally informative bar, full side (+/-V);
- only the first bar of a session (no prior close) and missing/zero volume
  are honest gaps.

The renamed `test_sigma_zero_move_full_attribution` pins the zero-variance
branch; `test_partial_window_uses_available_history` pins the lenient-window
rule explicitly so no future reader reintroduces the contradiction silently.
"""
import math

import pytest

from services.chart_cvd import estimate_cvd_from_bars


def test_constant_price_flat_delta():
    bars = [{"t": t, "c": 100.0, "v": 1000} for t in range(5)]
    out = estimate_cvd_from_bars(bars, window=20)
    # first bar UNKNOWN (gap), rest delta=0, CVD flat at 0
    assert out[0]["delta"] is None
    for o in out[1:]:
        assert o["delta"] == pytest.approx(0.0, abs=1e-9)


def test_huge_up_bar_positive_delta():
    bars = [{"t": 0, "c": 100.0, "v": 1000},
            {"t": 1, "c": 110.0, "v": 1000}]  # +10% on 100
    out = estimate_cvd_from_bars(bars, window=20)
    assert out[1]["delta"] > 900  # ~= V


def test_huge_down_bar_negative_delta():
    bars = [{"t": 0, "c": 100.0, "v": 1000},
            {"t": 1, "c": 90.0, "v": 1000}]
    out = estimate_cvd_from_bars(bars, window=20)
    assert out[1]["delta"] < -900  # ~= -V


def test_first_bar_gap():
    bars = [{"t": 0, "c": 100.0, "v": 1000}]
    out = estimate_cvd_from_bars(bars, window=20)
    assert out[0]["delta"] is None
    assert out[0]["cvd"] is None


def test_sigma_zero_move_full_attribution():
    # Zero variance with a real move: maximally informative bar takes the
    # full side. (Replaces the spec's self-contradictory sigma_zero_gap;
    # see module docstring for the documented rationale.)
    bars = [{"t": 0, "c": 100.0, "v": 1000},
            {"t": 1, "c": 100.0, "v": 1000},
            {"t": 2, "c": 105.0, "v": 1000}]
    out = estimate_cvd_from_bars(bars, window=20)
    assert out[0]["delta"] is None
    assert out[1]["delta"] == pytest.approx(0.0, abs=1e-9)
    assert out[2]["delta"] > 900


def test_partial_window_uses_available_history():
    # Window larger than history still classifies from available returns;
    # only the first bar (no prior close) is a gap.
    bars = [{"t": 0, "c": 100.0, "v": 1000},
            {"t": 1, "c": 101.0, "v": 1000},
            {"t": 2, "c": 102.0, "v": 1000}]
    out = estimate_cvd_from_bars(bars, window=20)
    assert out[0]["delta"] is None
    assert out[1]["delta"] is not None
    assert out[2]["delta"] is not None
    assert out[2]["cvd"] == pytest.approx(out[1]["cvd"] + out[2]["delta"])


def test_absent_volume_gap():
    bars = [{"t": 0, "c": 100.0}, {"t": 1, "c": 101.0, "v": 1000}]
    out = estimate_cvd_from_bars(bars, window=20)
    assert out[0]["delta"] is None
    assert out[1]["delta"] is not None


def test_zero_volume_gap():
    bars = [{"t": 0, "c": 100.0, "v": 1000},
            {"t": 1, "c": 101.0, "v": 0}]
    out = estimate_cvd_from_bars(bars, window=20)
    assert out[1]["delta"] is None
    assert out[1]["cvd"] is None


def test_session_reset():
    # two sessions separated by overnight; second session first bar is gap
    bars_day1 = [{"t": 34200, "c": 100.0, "v": 1000},
                 {"t": 34260, "c": 101.0, "v": 1000}]
    bars_day2 = [{"t": 70200, "c": 102.0, "v": 1000},
                 {"t": 70260, "c": 103.0, "v": 1000}]
    out1 = estimate_cvd_from_bars(bars_day1, window=20)
    out2 = estimate_cvd_from_bars(bars_day2, window=20)
    assert out2[0]["delta"] is None  # first bar of day 2 = gap
    assert out1[1]["delta"] is not None


def test_session_reset_within_one_call():
    # One call spanning two New York dates: the new session's first bar is
    # a gap and the overnight move never enters sigma.
    day1_open = 1787610600  # 2026-10-05 13:30 UTC (09:30 ET)
    day2_open = 1787697000  # 2026-10-06 13:30 UTC (09:30 ET)
    bars = [
        {"t": day1_open, "c": 100.0, "v": 1000},
        {"t": day1_open + 1800, "c": 101.0, "v": 1000},
        {"t": day2_open, "c": 150.0, "v": 1000},
        {"t": day2_open + 1800, "c": 151.0, "v": 1000},
    ]
    out = estimate_cvd_from_bars(bars, window=20)
    assert out[0]["delta"] is None
    assert out[1]["delta"] is not None
    assert out[2]["delta"] is None  # new session first bar = gap
    assert out[2]["cvd"] is None
    assert out[3]["delta"] is not None


def test_cvd_running_sum_only_over_known():
    bars = [{"t": t, "c": 100.0 + t, "v": 1000} for t in range(4)]
    out = estimate_cvd_from_bars(bars, window=20)
    total = 0.0
    for o in out:
        if o["delta"] is None:
            assert o["cvd"] is None
        else:
            total += o["delta"]
            assert o["cvd"] == pytest.approx(total)


def test_output_shape_and_time_passthrough():
    bars = [{"t": 10, "c": 100.0, "v": 1000},
            {"t": 20, "c": 101.0, "v": 2000}]
    out = estimate_cvd_from_bars(bars, window=20)
    assert len(out) == 2
    for _bar, o in zip(bars, out, strict=True):
        assert set(o) == {"time", "delta", "cvd"}
        assert math.isfinite(o["time"])


def test_build_history_cvd_line_aligns_to_frames():
    # Characterization pin for the build_history wiring: cvd_line rows match
    # frames one-to-one in order and time (index-zipped, never float-matched).
    from services.price_node_history import build_history
    day = 1787610600  # 2026-10-05 13:30 UTC, one New York session
    bars = [{"t": day + i * 1800, "o": 100 + i, "h": 101 + i,
             "l": 99 + i, "c": 100 + i, "v": 1000} for i in range(4)]
    out = build_history("SPY", bars, [])
    assert len(out["cvd_line"]) == len(out["frames"]) == 4
    for frame, row in zip(out["frames"], out["cvd_line"], strict=True):
        assert row["time"] == frame["time"]
        assert row["delta"] == frame["cvd_delta"]
        assert row["cvd"] == frame["cvd"]
    assert out["cvd_line"][0]["delta"] is None
    assert out["cvd_line"][0]["cvd"] is None
    assert out["cvd_line"][1]["delta"] is not None
