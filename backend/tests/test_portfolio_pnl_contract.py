"""Portfolio summary money contract.

The Portfolio panel reads ``pnl.total_pnl``, ``pnl.pct_pnl``,
``pnl.total_entry_value`` and ``pnl.total_current_value``, but the summary
endpoint returned ``pnl`` as a bare number, so the panel rendered
``undefined%`` for every P&L line. These tests pin:

* the object shape the panel consumes,
* the priced/skipped coverage split (an unusable position is disclosed, never
  silently dropped and never counted as a zero-valued position),
* the no-fabricated-value rule (an empty or unusable population is
  *unavailable*, not a measured zero),
* money accumulation through ``Decimal`` like ``Position.pnl`` does.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

VALID_POSITION = {
    "symbol": "SPY",
    "option_type": "call",
    "strike": 500.0,
    "expiry": "2030-12-20",
    "quantity": 2,
    "entry_price": 5.50,
    "entry_iv": 0.15,
    "underlying_price": 530.0,
}


async def _seed(aclient, name: str, positions: list[dict]) -> None:
    for pos in positions:
        r = await aclient.post(f"/api/portfolio/{name}/position", json=pos)
        assert r.status_code == 200, r.text


async def _cleanup(name: str) -> None:
    from server import db

    await db.portfolios.delete_one({"name": name})


async def test_summary_pnl_is_the_object_the_panel_consumes(aclient):
    name = "pnl-contract-shape"
    await _seed(aclient, name, [VALID_POSITION])
    try:
        r = await aclient.get(f"/api/portfolio/{name}?spot=530&iv=0.15")
        assert r.status_code == 200, r.text
        d = r.json()

        pnl = d["pnl"]
        assert isinstance(pnl, dict), "the panel reads pnl.total_pnl; a number cannot carry it"
        assert pnl["status"] == "ok"
        assert pnl["reason"] is None
        for key in ("total_pnl", "pct_pnl", "total_entry_value", "total_current_value"):
            assert key in pnl, f"missing {key}"
            assert isinstance(pnl[key], (int, float)), f"{key} must be a number"

        # 2 contracts x 100 multiplier x 5.50 entry
        assert pnl["total_entry_value"] == pytest.approx(1100.0)
        assert pnl["total_current_value"] == pytest.approx(
            pnl["total_entry_value"] + pnl["total_pnl"], rel=1e-9)
        assert pnl["pct_pnl"] == pytest.approx(
            pnl["total_pnl"] / pnl["total_entry_value"] * 100.0, abs=1e-3)

        # The numeric total stays available for older consumers.
        assert d["total_pnl"] == pytest.approx(pnl["total_pnl"])
    finally:
        await _cleanup(name)


async def test_unusable_position_is_disclosed_not_dropped(aclient):
    name = "pnl-contract-skipped"
    broken = dict(VALID_POSITION, strike=0.0, symbol="BAD")
    await _seed(aclient, name, [VALID_POSITION, broken])
    try:
        r = await aclient.get(f"/api/portfolio/{name}?spot=530&iv=0.15")
        assert r.status_code == 200, r.text
        d = r.json()

        assert d["positions"] == 2, "the stored position count must not shrink"
        assert d["positions_priced"] == 1
        assert d["positions_skipped"] == 1
        skipped = d["skipped"]
        assert len(skipped) == 1
        assert skipped[0]["reason"], "a skipped position needs a typed reason"
        assert skipped[0]["index"] == 1

        # The money covers the priced population only, and says so.
        assert d["pnl"]["status"] == "ok"
        assert d["pnl"]["total_entry_value"] == pytest.approx(1100.0)
        assert d["pnl"]["coverage"]["priced"] == 1
        assert d["pnl"]["coverage"]["skipped"] == 1
    finally:
        await _cleanup(name)


async def test_empty_book_is_unavailable_not_zero(aclient):
    name = "pnl-contract-empty"
    from server import db

    await db.portfolios.insert_one({"name": name, "positions": []})
    try:
        r = await aclient.get(f"/api/portfolio/{name}?spot=530&iv=0.15")
        assert r.status_code == 200, r.text
        d = r.json()

        pnl = d["pnl"]
        assert pnl["status"] == "unavailable"
        assert pnl["reason"] == "NO_PRICED_POSITIONS"
        assert pnl["total_pnl"] is None, "an empty population is not a measured zero"
        assert pnl["total_entry_value"] is None
        assert pnl["pct_pnl"] is None
        assert d["total_pnl"] is None
    finally:
        await _cleanup(name)


async def test_summary_declares_its_valuation_basis_and_multiplier(aclient):
    name = "pnl-contract-basis"
    await _seed(aclient, name, [VALID_POSITION])
    try:
        r = await aclient.get(f"/api/portfolio/{name}?spot=530&iv=0.15")
        d = r.json()

        assert d["valuation_basis"] == "local_bs_model_at_spot_iv"
        assert d["spot"] == pytest.approx(530.0)
        assert d["iv"] == pytest.approx(0.15)
        mult = d["pnl"]["multiplier"]
        assert mult["value"] == 100
        assert mult["source"], "the contract multiplier must declare its source"
        assert d["pnl"]["currency"] == "USD"
    finally:
        await _cleanup(name)
