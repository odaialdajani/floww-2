import pytest

from services.agent.contracts import fact, request_spec, validate_model_answer


@pytest.mark.parametrize("kind,accepted", [("above", False), ("below", True), ("fresh", True), ("stale", False)])
def test_relationships_must_match_actual_saved_values(kind, accepted):
    ledger = {
        name: fact(
            metric, value, "USD", ticker="SPY", source="fixture", snapshot_id="s", event_time="2026-09-11T15:00:00Z"
        )
        for name, metric, value in [("spot", "Underlying price", 95), ("flip", "Gamma flip", 100)]
    }
    relation = {"kind": kind, "fact_id": "spot"}
    if kind in {"above", "below"}:
        relation["other_fact_id"] = "flip"
    answer = {
        "sections": [{"name": "Structure", "fact_ids": ["spot", "flip"], "interpretation": "descriptive"}],
        "relationships": [relation],
    }
    if accepted:
        assert validate_model_answer(answer, ledger)["relationship_text"]
    else:
        with pytest.raises(ValueError):
            validate_model_answer(answer, ledger)


@pytest.mark.parametrize("bad", [[{}], [[1]], {"nested": 1}])
def test_nested_fact_values_are_rejected(bad):
    with pytest.raises(ValueError):
        fact("value", bad, "USD", ticker="SPY", source="fixture", snapshot_id="s")


@pytest.mark.parametrize("section", [["name"], None, 4])
def test_malformed_sections_reject_without_an_unhandled_error(section):
    with pytest.raises(ValueError):
        validate_model_answer({"sections": [section]}, {})


def test_fact_digest_covers_values_beyond_old_truncation():
    first = fact("series", list(range(100)), "USD", ticker="SPY", source="fixture", snapshot_id="s")
    changed = fact("series", list(range(99)) + [999], "USD", ticker="SPY", source="fixture", snapshot_id="s")
    assert first["id"] != changed["id"]


def test_unknown_source_time_is_degraded_not_fresh():
    f = fact("spot", 123.4, "USD", ticker="SPY", source="fixture", snapshot_id="s", received_at="2026-09-11T10:00:00Z")
    assert f["status"] == "degraded"
    assert f["event_time"] is None


def test_explicit_question_ticker_wins_without_relabelling_context():
    spec = request_spec(
        {
            "question": "What about $QQQ?",
            "ticker": "SPY",
            "screen": {"ticker": "SPY", "selectedContract": "SPY-contract"},
        }
    )
    assert spec["tickers"] == ["QQQ"]
    assert spec["screen"]["ticker"] == "SPY"
    assert spec["context_conflict"]


@pytest.mark.parametrize(
    "question,horizon,expiry",
    [
        ("Use contracts expiring today for MSFT", "0dte", None),
        ("Use the next five trading sessions for MSFT", "week", None),
        ("Explain MSFT expiry 2026-10-16", "all", "2026-10-16"),
    ],
)
def test_question_expiry_scope_wins_but_original_screen_remains_saved(question, horizon, expiry):
    screen = {"ticker": "MSFT", "horizon": "month", "selectedExpiry": "2026-09-18"}
    spec = request_spec({"question": question, "screen": screen})
    assert spec["horizon"] == horizon
    assert spec["question_scope"]["selected_expiry"] == expiry
    assert spec["screen"] == screen


def test_observation_date_does_not_change_expiry_and_same_ticker_keeps_range():
    spec = request_spec(
        {"question": "What changed today since the last close?", "screen": {"ticker": "DIA", "horizon": "month"}}
    )
    assert spec["horizon"] == "month" and spec["question_scope"] is None
    spec = request_spec({"question": "Explain DIA", "screen": {"ticker": "DIA", "expiryRange": [3, 12]}})
    assert spec["horizon"] == "range:3:12"


@pytest.mark.parametrize("text", ["The price is 999", "Price is above flip", "This is guaranteed bullish"])
def test_model_cannot_hide_factual_claims_in_commentary(text):
    with pytest.raises(ValueError):
        validate_model_answer(
            {"sections": [{"name": "Structure", "fact_ids": ["spot"], "commentary": text}]},
            {"spot": {"value": 1, "ticker": "SPY"}},
        )
