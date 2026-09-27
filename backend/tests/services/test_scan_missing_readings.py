from unittest.mock import patch

import pytest

from services.flow_alerts import norm_rows
from services.journal_store import whale_state
from services.public_scanner import unusual_rows_from_chain


@pytest.mark.parametrize("oi", [None, 0, -1, float("nan"), float("inf")])
def test_missing_or_zero_oi_never_creates_unusual_ratio(oi):
    contract = {"osi":"TEST", "type":"call", "strike":100, "expiry":"2026-10-30", "volume":300, "oi":oi, "iv":None}
    rows, _ = unusual_rows_from_chain({"ticker":"TEST", "spot":None, "contracts":[contract]})
    assert rows == []
    contract["volume"] = 3000
    rows, _ = unusual_rows_from_chain({"ticker":"TEST", "spot":None, "contracts":[contract]})
    assert len(rows) == 1
    assert rows[0][6] == (0 if oi == 0 else None)
    assert rows[0][7] is None and rows[0][9] is None
    normalized = norm_rows(rows)
    assert len(normalized) == 1
    assert normalized[0]["vol_oi"] is None
    assert normalized[0]["oi"] == rows[0][6]
    assert normalized[0]["premium"] is None

@pytest.mark.parametrize("missing", ["entry_oi", "oi"])
def test_whale_unknown_oi_does_not_claim_held(missing):
    track = {"entry_oi":1000, "entry_spot":100, "entry_vol":500}
    snap = {"oi":1000, "spot":101, "vol":500, "dte":10}
    (track if missing == "entry_oi" else snap)[missing] = None
    assert whale_state(track, snap)["state"] == "UNKNOWN"


@pytest.mark.asyncio
async def test_scan_saving_skips_absent_oi_but_preserves_real_zero(monkeypatch):
    import sys
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from routes.flowseeker import _record_scan_baseline
    daily = SimpleNamespace(update_one=AsyncMock())
    contracts = SimpleNamespace(bulk_write=AsyncMock())
    monkeypatch.setitem(sys.modules, "server", SimpleNamespace(db=SimpleNamespace(flow_scan_daily=daily, flow_scan_contract_oi=contracts)))
    rows = [["TEST", "MISSING", "call", 100, "2026-10-30", 3000, None, None, None, None],
            ["TEST", "ZERO", "call", 100, "2026-10-30", 3000, 0, None, None, None]]
    await _record_scan_baseline(rows)
    daily.update_one.assert_awaited_once()
    contracts.bulk_write.assert_awaited_once()
    operations = contracts.bulk_write.call_args.args[0]
    assert len(operations) == 1
    assert operations[0]._filter["ticker"] == "ZERO"
    assert operations[0]._doc["$max"]["oi"] == 0


@pytest.mark.parametrize("volume", [None, "bad", float("inf"), float("nan"), -1])
def test_invalid_volume_cannot_crash_or_create_a_scan_reading(volume):
    rows, _ = unusual_rows_from_chain({"ticker":"TEST", "contracts":[{
        "type":"call", "strike":100, "expiry":"2026-10-30", "oi":None, "volume":volume}]})
    assert rows == []


def test_measured_zero_is_not_described_as_missing():
    from services.flow_alerts import build_context
    summary = build_context({"oi":0, "vol":3000, "vol_oi":None}, {})["activity_summary"]
    assert "0 open interest" in summary
    assert "volume/OI unavailable" in summary
    assert "open interest unavailable" not in summary
    reason = whale_state({"entry_oi":0}, {"oi":50, "dte":10})["reason"]
    assert "initial open interest was zero" in reason.lower()
    assert "unavailable" not in reason.lower()
