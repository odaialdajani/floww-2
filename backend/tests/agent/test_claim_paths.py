import pytest

from services.agent.claims import claim_seed, resolve_claim
from services.agent.contracts import fact


def seed(**changes):
    return claim_seed(
        turn_id="turn",
        ticker="SPY",
        issued_at="2026-09-11T15:00:00Z",
        deadline="2026-09-11T15:02:00Z",
        reference=100,
        target=103,
        invalidation=97,
        direction="up",
        evidence=[
            fact(
                "Underlying price",
                100,
                "USD",
                ticker="SPY",
                source="synthetic fixture",
                snapshot_id="fixture",
                event_time="2026-09-11T15:00:00Z",
                received_at="2026-09-11T15:00:00Z",
            )
        ],
        **changes,
    )


def bar(minute, high=102, low=98):
    return {
        "start": f"2026-09-11T15:0{minute}:00Z",
        "end": f"2026-09-11T15:0{minute + 1}:00Z",
        "open": 100,
        "close": 100,
        "high": high,
        "low": low,
        "source": "synthetic fixture",
        "ticker": "SPY",
        "bar_id": str(minute),
    }


@pytest.mark.parametrize(
    "bars,status",
    [
        ([bar(0, 104), bar(1)], "win"),
        ([bar(0, 102, 96), bar(1)], "loss"),
        ([bar(0, 104, 96)], "ambiguous"),
        ([bar(0), bar(1)], "neither"),
        ([bar(1, 104)], "missing_data"),
        ([], "missing_data"),
    ],
)
def test_path_outcomes_do_not_assume_target_first_or_fill_gaps(bars, status):
    assert resolve_claim(seed(), bars, now="2026-09-11T15:03:00Z")["status"] == status


def test_midbar_issuance_and_trigger_order_are_not_hindsight_wins():
    args = {key: value for key, value in seed().items() if key not in {"claim_id", "version", "confidence_meaning"}}
    changed = claim_seed(**{**args, "issued_at": "2026-09-11T15:00:30Z"})
    assert resolve_claim(changed, [bar(0, 104)], now="2026-09-11T15:03:00Z")["status"] == "missing_data"
    assert resolve_claim(seed(trigger=101), [bar(0, 104)], now="2026-09-11T15:03:00Z")["status"] == "ambiguous"
    assert resolve_claim(seed(trigger=102.5), [bar(0), bar(1)], now="2026-09-11T15:03:00Z")["status"] == "untriggered"


def test_missing_provider_cannot_resolve_a_claim_and_corrections_change_digest():
    assert resolve_claim(seed(), [], now="2026-09-11T15:01:00Z", source_available=False)["status"] == "open"
    assert resolve_claim(seed(), [], now="2026-09-11T15:03:00Z", source_available=False)["status"] == "missing_data"
    first = resolve_claim(seed(), [bar(0, 104)], now="2026-09-11T15:03:00Z")
    corrected = resolve_claim(seed(), [bar(0, 104, 96)], now="2026-09-11T15:03:00Z")
    assert first["path_digest"] != corrected["path_digest"]


def test_conflicting_correction_is_checked_before_returning_a_win():
    assert resolve_claim(seed(), [bar(0, 104), bar(0, 102, 96)], now="2026-09-11T15:03:00Z")["status"] == "missing_data"


@pytest.mark.parametrize("observed", [None, "2026-09-11T15:01:00Z"])
def test_claim_rejects_unknown_or_future_evidence(observed):
    args = seed()
    for key in ("claim_id", "version", "confidence_meaning"):
        args.pop(key)
    args["evidence"][0]["event_time"] = observed
    with pytest.raises(ValueError):
        claim_seed(**args)


def test_nonfinite_path_is_malformed_instead_of_throwing():
    assert resolve_claim(seed(), [bar(0, float("nan"))], now="2026-09-11T15:03:00Z")["status"] == "malformed"


def test_mutated_claim_or_wrong_ticker_path_cannot_be_graded():
    assert resolve_claim({**seed(), "target": 99}, [bar(0, 104)], now="2026-09-11T15:03:00Z")["status"] == "malformed"
    assert (
        resolve_claim(seed(), [{**bar(0, 104), "ticker": "QQQ"}], now="2026-09-11T15:03:00Z")["status"] == "malformed"
    )


@pytest.mark.parametrize("received", [None, "2026-09-11T15:05:00Z"])
def test_claim_rejects_later_or_unknown_availability(received):
    args = seed()
    for key in ("claim_id", "version", "confidence_meaning"):
        args.pop(key)
    args["evidence"][0] = fact(
        "Underlying price",
        100,
        "USD",
        ticker="SPY",
        source="synthetic fixture",
        snapshot_id="fixture",
        event_time="2026-09-11T15:00:00Z",
        received_at=received,
    )
    with pytest.raises(ValueError):
        claim_seed(**args)
