"""
backend/tests/test_bs_greeks_masking.py

B4 (silent-masking observability): the Black-Scholes helpers in bs_greeks.py
catch *all* exceptions and return 0.0. A 0.0 from the guard clause (expired /
invalid contract) is legitimate; a 0.0 from an UNEXPECTED error is a silent
failure indistinguishable from "no gamma here", which biases aggregate GEX
toward zero with no signal.

Contract pinned here:
  * behavior is preserved -- a masked error still returns 0.0 (so the frozen
    ML-feature path and every caller see identical values), AND
  * the masking is now OBSERVABLE -- a WARNING is logged so it can be detected
    in production instead of vanishing.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bs_greeks  # noqa: E402


def test_bs_gamma_guard_clause_returns_zero_silently():
    """Invalid input -> 0.0 with NO warning (legitimate, not a masked error)."""
    import logging

    records = []
    handler = logging.Handler()
    handler.emit = lambda r: records.append(r)
    logging.getLogger("bs_greeks").addHandler(handler)
    try:
        assert bs_greeks.bs_gamma(100.0, 100.0, -1.0, 0.20) == 0.0  # T<=0 guard
    finally:
        logging.getLogger("bs_greeks").removeHandler(handler)
    assert records == [], "guard-clause zero must not emit a warning"


def test_bs_gamma_masked_error_still_returns_zero(monkeypatch):
    """An unexpected internal error preserves the 0.0 return (no behavior change)."""
    def boom(*_a, **_k):
        raise RuntimeError("synthetic numerical failure")

    monkeypatch.setattr(bs_greeks.norm, "pdf", boom)
    # Inputs pass the guard clause, so the error fires inside the try/except.
    assert bs_greeks.bs_gamma(100.0, 100.0, 0.5, 0.20) == 0.0


def test_bs_gamma_masked_error_is_observable(monkeypatch, caplog):
    """An unexpected internal error is logged at WARNING (no longer silent)."""
    def boom(*_a, **_k):
        raise RuntimeError("synthetic numerical failure")

    monkeypatch.setattr(bs_greeks.norm, "pdf", boom)
    with caplog.at_level("WARNING", logger="bs_greeks"):
        bs_greeks.bs_gamma(100.0, 100.0, 0.5, 0.20)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "masked error must emit a WARNING"
    assert any("gamma" in r.getMessage().lower() for r in warnings)
