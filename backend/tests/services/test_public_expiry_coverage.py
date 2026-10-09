"""Usable expiry coverage comes from accepted contracts, not request success."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from services import public_api_adapter as adapter
from tests.services.test_public_adapter_truth import make_broker, make_contract


async def fetch_admitted(broker, max_expiries):
    """Exercise skip recovery under the owning wrapper's real admission contract."""
    from services.public_budget import PublicBudget

    budget = PublicBudget(capacity=60, refill_per_sec=0, max_inflight=4)
    with patch.object(adapter, "BROKER", broker), \
         patch.object(adapter, "_get_broker", AsyncMock(return_value=broker)), \
         patch.object(adapter, "_CHAIN_CACHE", {}), \
         patch.object(adapter._public_budget, "budget", budget):
        result = await adapter.fetch_chain_from_public_api("SPY", max_expiries)
        assert budget._inflight == 0
        return result


async def fetch_mocked(chains):
    broker = make_broker(chains)
    with patch.object(adapter, "_resolve_spot_observation", AsyncMock(return_value={
        "price": 520.5, "source": "public-mid", "event_time": None,
        "fetched_at": datetime.now(UTC).isoformat(),
    })):
        return await adapter._fetch_chain_live(broker, "SPY", len(chains))


@pytest.mark.asyncio
async def test_successful_empty_expiry_is_not_available_coverage():
    today = datetime.now(UTC).date()
    empty = (today + timedelta(days=7)).isoformat()
    usable = (today + timedelta(days=14)).isoformat()
    result = await fetch_mocked({empty: [], usable: [make_contract(expiration=usable)]})
    assert result["expiries"] == [usable]
    assert {c["expiry"] for c in result["contracts"]} == {usable}
    assert result["skipped"] == [{"expiry": empty, "reason": "NO_ADMITTED_CONTRACTS"}]


@pytest.mark.asyncio
async def test_ordinary_chain_reports_failed_expiry_to_exposure_consumer():
    today = datetime.now(UTC).date()
    failed = (today + timedelta(days=7)).isoformat()
    usable = (today + timedelta(days=14)).isoformat()
    broker = make_broker({failed: [], usable: [make_contract(expiration=usable)]})
    original = broker.get_option_chain_parsed.side_effect

    async def fetch(symbol, expiry, account_id, **kwargs):
        if str(expiry) == failed:
            raise RuntimeError("synthetic failed expiry")
        return original(symbol, expiry, account_id)

    broker.get_option_chain_parsed.side_effect = fetch
    with patch.object(adapter, "_resolve_spot_observation", AsyncMock(return_value={
        "price": 520.5, "source": "synthetic-mid", "event_time": None,
        "fetched_at": "2026-10-07T14:01:00Z",
    })):
        result = await adapter._fetch_chain_live(broker, "SPY", 2)
    assert result["skipped"] == [{"expiry": failed, "reason": "CHAIN_FETCH_FAILED"}]
    from services.triad_projection import exposure_by_strike

    series = exposure_by_strike(result)
    assert series["source_coverage"]["skipped"] == result["skipped"]
    assert series["fetched_at"] == result["fetched_at"]


@pytest.mark.asyncio
async def test_all_rejected_expiry_does_not_leak_into_available_coverage():
    today = datetime.now(UTC).date()
    rejected = (today + timedelta(days=7)).isoformat()
    usable = (today + timedelta(days=14)).isoformat()
    result = await fetch_mocked({
        rejected: [make_contract(expiration=(today - timedelta(days=1)).isoformat()),
                   make_contract(expiration=rejected, strike=float("nan")),
                   make_contract(expiration="invalid")],
        usable: [make_contract(expiration=usable)],
    })
    assert result["expiries"] == [usable]
    assert len(result["contracts"]) == 1


@pytest.mark.asyncio
async def test_mixed_response_uses_actual_accepted_expiry_and_keeps_zero_dte(monkeypatch):
    class TradingDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 11, 15, tzinfo=UTC)

    monkeypatch.setattr(adapter, "datetime", TradingDateTime)
    today = TradingDateTime.now(UTC).date()
    requested = (today + timedelta(days=7)).isoformat()
    actual = (today + timedelta(days=14)).isoformat()
    result = await fetch_mocked({requested: [
        make_contract(expiration=actual), make_contract(expiration=actual, strike=531),
        make_contract(expiration=today.isoformat()), make_contract(expiration="bad"),
    ]})
    assert result["expiries"] == [actual, today.isoformat()]
    assert {c["expiry"] for c in result["contracts"]} == set(result["expiries"])
    assert len(result["contracts"]) == 3


@pytest.mark.asyncio
async def test_max_expiries_window_skips_expiries_with_no_accepted_contracts(monkeypatch):
    """A 1-expiry request must not be spent on an expiry that yields nothing.

    After the close, the vendor's expiry list still leads with TODAY, whose
    contracts are all dropped as EXPIRED. Slicing `expiries[:max_expiries]`
    before the per-contract filter spent the whole budget on that dead expiry
    and returned None, which surfaced as a 503 from /api/spot/{ticker} — even
    though the very next expiry held a full chain.
    """

    class AfterCloseDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            # 16:30 ET: today's 0DTE is expired, tomorrow is not.
            return cls(2026, 9, 29, 20, 30, tzinfo=UTC)

    monkeypatch.setattr(adapter, "datetime", AfterCloseDateTime)
    today = AfterCloseDateTime.now(UTC).date().isoformat()
    tomorrow = (AfterCloseDateTime.now(UTC).date() + timedelta(days=1)).isoformat()
    broker = make_broker({
        today: [make_contract(expiration=today)],
        tomorrow: [make_contract(expiration=tomorrow, strike=531.0)],
    })
    with patch.object(adapter, "_resolve_spot_observation", AsyncMock(return_value={
        "price": 530.0, "source": "public-mid", "event_time": None,
        "fetched_at": AfterCloseDateTime.now().isoformat(),
    })):
        result = await fetch_admitted(broker, 1)

    assert result is not None, "an empty 1-expiry window must not 503 when a live expiry follows"
    assert result["expiries"] == [tomorrow]
    assert {c["expiry"] for c in result["contracts"]} == {tomorrow}


@pytest.mark.asyncio
async def test_attempts_stay_within_the_pre_debited_envelope(monkeypatch):
    """Walking past dead expiries must not exceed the pre-debited envelope.

    fetch_chain_from_public_api pre-debits a FIXED `2 + max_expiries` envelope
    before any provider call (C8). Bounding max_expiries by ACCEPTED expiries
    means skipping leading dead ones, so the walk needs its OWN attempt bound.
    Without it, a vendor list led by expired expiries makes actual provider
    calls outrun the debit, and the shared-quota pre-debit silently becomes an
    under-count -- reported in .planning/INTEGRATION_PUBLIC_EXPIRY_ENVELOPE.md.

    The fixture leads with MAX_EXPIRY_SKIPS+1 expired expiries, so an
    unbounded walk must try more than max_expiries + MAX_EXPIRY_SKIPS and be
    caught by the cap.
    """

    class AfterCloseDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 29, 20, 30, tzinfo=UTC)  # 16:30 ET

    monkeypatch.setattr(adapter, "datetime", AfterCloseDateTime)
    base = AfterCloseDateTime.now(UTC).date()
    n_dead = adapter.MAX_EXPIRY_SKIPS + 1  # one more than the cap allows
    dead = [(base - timedelta(days=k)).isoformat() for k in range(1, n_dead + 1)]
    live = (base + timedelta(days=30)).isoformat()
    ordered = dead + [live]
    chains = {d: [make_contract(expiration=d)] for d in ordered}
    broker = make_broker(chains)

    seen = []
    original = broker.get_option_chain_parsed

    async def recording(symbol, expiration, account_id, **kw):
        seen.append(expiration)
        return await original(symbol, expiration, account_id)

    broker.get_option_chain_parsed = recording

    with patch.object(adapter, "_resolve_spot_observation", AsyncMock(return_value={
        "price": 530.0, "source": "public-mid", "event_time": None,
        "fetched_at": AfterCloseDateTime.now().isoformat(),
    })):
        # The call is what performs the walk; the assertion is on the count.
        await fetch_admitted(broker, 1)

    # One chain call per attempt. This is the assertion that fails when the
    # walk is unbounded: an unbounded loop would try every dead expiry.
    assert len(seen) == 1 + adapter.MAX_EXPIRY_SKIPS
    assert len(seen) <= 1 + adapter.MAX_EXPIRY_SKIPS, (
        f"walked {len(seen)} expiries, over the pre-debited envelope "
        f"(1 + {adapter.MAX_EXPIRY_SKIPS}): {seen}"
    )


@pytest.mark.asyncio
async def test_one_dead_expiry_is_skipped_and_the_live_one_is_returned(monkeypatch):
    """The original 503 fix, pinned: one dead leading expiry is not fatal."""
    from datetime import UTC, datetime, timedelta

    class AfterCloseDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 29, 20, 30, tzinfo=UTC)

    monkeypatch.setattr(adapter, "datetime", AfterCloseDateTime)
    base = AfterCloseDateTime.now(UTC).date()
    today = base.isoformat()
    live = (base + timedelta(days=1)).isoformat()
    broker = make_broker({
        today: [make_contract(expiration=today)],
        live: [make_contract(expiration=live, strike=531.0)],
    })
    with patch.object(adapter, "_resolve_spot_observation", AsyncMock(return_value={
        "price": 530.0, "source": "public-mid", "event_time": None,
        "fetched_at": AfterCloseDateTime.now().isoformat(),
    })):
        result = await fetch_admitted(broker, 1)
    assert result is not None, "a 1-expiry request must not 503 when a live expiry follows"
    assert result["expiries"] == [live]


@pytest.mark.asyncio
async def test_no_accepted_contracts_remains_unavailable():
    result = await fetch_mocked({"bad": [], "also-bad": [make_contract(expiration="invalid")]})
    assert result is None


@pytest.mark.asyncio
async def test_index_contract_uses_its_own_root_on_monthly_expiry(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 16, 14, tzinfo=UTC)

    monkeypatch.setattr(adapter, "datetime", FixedDateTime)
    expiry = "2026-10-16"
    broker = make_broker({expiry: [
        make_contract(symbol="SPXW261016C06000000", expiration=expiry, strike=6000),
        make_contract(symbol="SPX261016C06000000", expiration=expiry, strike=6000),
    ]})
    with patch.object(adapter, "_resolve_spot_observation", AsyncMock(return_value={
        "price": 6000, "source": "public-mid", "event_time": None,
        "fetched_at": FixedDateTime.now().isoformat(),
    })):
        result = await adapter._fetch_chain_live(broker, "^SPX", 1)
    assert result is not None
    assert [c["osi"] for c in result["contracts"]] == ["SPXW261016C06000000"]
    assert result["contracts"][0]["series"] == "SPXW"
    assert result["contracts"][0]["T"] == pytest.approx(6 / (24 * 365))
