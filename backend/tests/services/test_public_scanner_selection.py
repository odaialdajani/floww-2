"""Bounded ratio/size retention must not hide eligible large-volume contracts."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from services import public_scanner as scanner


def contract(index, volume=200, oi=1):
    return dict(osi=f"TEST261016C{index:08d}", type="call", strike=100 + index,
                expiry="2026-10-16", volume=volume, oi=oi, iv=.3, delta=.5)


@pytest.mark.parametrize("oi", [10000, None, 0])
def test_large_volume_survives_sixty_small_ratio_leaders(oi):
    tiny = [contract(i) for i in range(60)]
    large = contract(60, volume=25000, oi=oi)
    rows, extras = scanner.unusual_rows_from_chain(dict(ticker="TEST", spot=100, contracts=tiny + [large]))
    visible = [row for row in rows if row[5] >= 1000]
    assert [row[1] for row in visible] == [large["osi"]]
    assert {row[1] for row in rows[:60]} == {item["osi"] for item in tiny}
    assert len({scanner.ckey_of(row[0], row[2], row[3], row[4]) for row in rows}) == len(rows)
    assert len(extras) == len(rows)
    assert visible[0][6] == oi


@pytest.mark.asyncio
@pytest.mark.parametrize("many", [False, True])
async def test_selection_reports_actual_union_bound_and_truncation(monkeypatch, many):
    scanner._reset_state()
    monkeypatch.setattr(scanner, "_get_adv", None)
    contracts = [contract(i) for i in range(60)]
    if many:
        contracts += [contract(i + 60, volume=30000, oi=300000) for i in range(60)]
        contracts.append(contract(120, volume=500, oi=100))
    chain = dict(ticker="TEST", spot=100, contracts=contracts, fetched_at=datetime.now(UTC).isoformat(), stale=False)
    monkeypatch.setattr("services.public_api_adapter.fetch_chain_from_public_api", AsyncMock(return_value=chain))
    try:
        pack = (await scanner.scan_slice(["TEST"]))["TEST"]
        assert len(pack["rows"]) == (120 if many else 60)
        assert pack["rows_capped"] is many
        assert pack["selection"]["eligible_rows"] == len(contracts)
        assert pack["selection"]["retained_rows"] == len(pack["rows"])
        assert pack["selection"]["rows_per_ticker_cap"] == 120
        assert pack["selection"]["ratio_leaders_limit"] == 60
        assert pack["selection"]["volume_leaders_limit"] == 60
    finally:
        scanner._reset_state()


def test_volume_union_preserves_conflicting_identity_exclusion():
    standard = contract(0, volume=400, oi=1)
    adjusted = {**standard, "osi": "TEST1261016C00000000", "volume": 25000, "oi": None}
    healthy = contract(1, volume=26000, oi=10000)
    rows, extras = scanner.unusual_rows_from_chain(dict(ticker="TEST", spot=100, contracts=[standard, adjusted, healthy]))
    # Existing display keys cannot distinguish the conflicting roots. Neither
    # may be restored merely because its volume qualifies for the new union.
    assert [row[1] for row in rows] == [healthy["osi"]]
    assert set(extras) == {scanner.ckey_of("TEST", "call", healthy["strike"], healthy["expiry"])}
