"""Focused regression — deterministic replay slippage (paper-recovery B2).

``PaperTradingEngine.execute_order`` derived its slippage from
``hash(order_id)``, which Python salts per process (PYTHONHASHSEED): the same
order history replayed in two processes produced DIFFERENT fills, so paper
P&L was not reproducible. RED on the pre-fix tree (seed-0 vs seed-1 subprocess
vectors disagree); GREEN after deriving the same bounded factor from a stable
sha256 digest — magnitude and bounds preserved EXACTLY (same ``% 100 - 50``
arithmetic over 0..99, |factor| <= 1.0, i.e. at most 1 bp of the fill price).

Two fresh in-process engines and one subprocess pair; no network, no Mongo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.execution_engine import MarketState  # noqa: E402
from services.paper_trading import PaperTradingEngine  # noqa: E402

BACKEND = str(Path(__file__).resolve().parents[2])

_SCRIPT = """
import json, sys
sys.path.insert(0, sys.argv[1])
from services.execution_engine import MarketState
from services.paper_trading import PaperTradingEngine
eng = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
m = MarketState(symbol="SPY", bid=100.0, ask=100.0, last=100.0, bid_size=100,
                ask_size=100, volume=1_000_000, volatility=0.2)
rows = []
for _ in range(32):
    oid = eng.submit_order(symbol="SPY", side="buy", quantity=1, market=m)["order_id"]
    result = eng.execute_order(oid, m)
    rows.append([result.order_id, repr(result.avg_price), result.slippage_bps])
print(json.dumps(rows))
"""


def _run_with_hash_seed(seed: str) -> list:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    out = subprocess.run(
        [sys.executable, "-c", _SCRIPT, BACKEND],
        capture_output=True, text=True, env=env, timeout=120, check=True,
    )
    return json.loads(out.stdout)


def _market():
    return MarketState(symbol="SPY", bid=100.0, ask=100.0, last=100.0, bid_size=100,
                       ask_size=100, volume=1_000_000, volatility=0.2)


def test_slippage_is_process_independent():
    """Same order ids must produce the same fills in every process."""
    seed0 = _run_with_hash_seed("0")
    seed1 = _run_with_hash_seed("1")
    assert seed0 == seed1, (
        "replay slippage differs across PYTHONHASHSEED processes — "
        "paper ledger is not deterministic"
    )


def test_slippage_bounds_preserved():
    """Magnitude/bounds stay exactly the pre-fix class: <= 1 bp of the fill."""
    rows = _run_with_hash_seed("random")
    assert len(rows) == 32
    for _order_id, _avg, bps in rows:
        assert 0.0 <= bps <= 1.0, bps


def test_same_process_replay_is_stable():
    """Two engines fed identical inputs produce identical execution records."""
    def _run():
        eng = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        m = _market()
        oid = eng.submit_order(symbol="SPY", side="buy", quantity=1, market=m)["order_id"]
        return eng.execute_order(oid, m)

    a, b = _run(), _run()
    assert a.avg_price == b.avg_price
    assert a.slippage_bps == b.slippage_bps
