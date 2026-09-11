from services.agent.answer_sections import SECTION_NAMES, merge_history_section
from services.agent.contracts import fact
from services.agent.research import deterministic_answer


def reading(metric, value, unit="USD", ticker="SPY", horizon="all", status="ok"):
    return fact(metric, value, unit, ticker=ticker, horizon=horizon, status=status,
                source="saved fixture", snapshot_id=ticker+horizon,
                event_time="2026-09-11T15:00:00Z")


def snapshot(ticker="SPY", horizon="all", price=100):
    return {"ticker": ticker, "horizon": horizon, "window": {}, "gaps": [], "facts": [
        reading("Underlying price", price, ticker=ticker, horizon=horizon),
        reading("Total estimated gamma exposure", 1000, ticker=ticker, horizon=horizon),
        reading("Estimated flip levels", [98, 105], ticker=ticker, horizon=horizon)]}


def spec(question="Full research", **kw):
    return {"question": question, "screen": {}, "tickers": ["SPY"], **kw}


def test_full_answer_values_and_explicit_unavailable_sections():
    answer = deterministic_answer([snapshot()], spec())
    assert [s["name"] for s in answer["sections"]] == list(SECTION_NAMES)
    sections = {s["name"]: s for s in answer["sections"]}
    assert "1,000 USD" in sections["Structure"]["text"]
    assert "98, 105 USD" in sections["Levels"]["text"]
    assert sections["Company"]["status"] == "unavailable"
    assert "No event date" in sections["Company"]["text"]
    assert "No executable trade" in sections["Trade"]["text"]
    assert "Insufficient evidence" in sections["Verdict"]["text"]
    assert all(s["claim_status"] == "non-gradeable" for s in answer["sections"])


def test_quick_flow_and_price_omit_unrelated_sections():
    snap = snapshot()
    snap["facts"].append(reading("Signed alert reading", -.4, "signed agreement"))
    answer = deterministic_answer([snap], spec("Show flow"))
    assert [s["name"] for s in answer["sections"]] == ["Flow"]
    assert "-0.4 signed agreement" in answer["sections"][0]["text"]
    price = deterministic_answer([snap], spec("SPY underlying price", price_only=True))
    assert len(price["sections"]) == 1
    assert "100 USD" in price["sections"][0]["text"]
    assert "gamma" not in price["sections"][0]["text"]
    assert price["sections"][0]["fact_ids"] == [snap["facts"][0]["id"]]


def test_multi_ticker_horizon_references_stay_separate():
    answer = deterministic_answer([snapshot(), snapshot("QQQ", "0dte", 450)], spec(tickers=["SPY", "QQQ"]))
    entries = answer["sections"][0]["entries"]
    assert [(e["ticker"], e["horizon"]) for e in entries] == [("SPY", "all"), ("QQQ", "0dte")]
    assert "Underlying price: 100 USD" in entries[0]["text"]
    assert "Underlying price: 450 USD" in entries[1]["text"]
    by_id = {f["id"]: f for f in answer["facts"]}
    for section in answer["sections"]:
        for entry in section["entries"]:
            for segment in entry["segments"]:
                if segment["type"] == "fact_reference":
                    source = by_id[segment["fact_id"]]
                    assert segment["ticker"] == source["ticker"] == entry["ticker"]
                    assert segment["horizon"] == source["horizon"]


def test_stale_source_not_upgraded():
    snap = snapshot()
    snap["facts"] = [reading("Signed alert reading", .7, "signed agreement", status="stale")]
    section = deterministic_answer([snap], spec("flow"))["sections"][0]
    assert section["status"] == "degraded"
    assert "stale; observed" in section["text"]


def test_volatility_values_and_missing_levels_are_honest():
    snap = snapshot()
    snap["facts"] = [reading("Underlying price", 100), reading("Implied move estimate", 3.25),
                     reading("At-the-money implied volatility", .24, "fraction", status="degraded")]
    snap["gaps"] = ["Company source unavailable"]
    answer = deterministic_answer([snap], spec())
    sections = {s["name"]: s for s in answer["sections"]}
    assert "3.25 USD" in sections["Vol"]["text"]
    assert "0.24 fraction" in sections["Vol"]["text"]
    assert sections["Vol"]["status"] == "degraded"
    assert sections["Levels"]["status"] == "unavailable"
    assert "no level was established" in sections["Levels"]["text"]
    assert sections["Vol"]["entries"][0]["source_gaps"] == snap["gaps"]


def test_history_merges_without_erasing_other_ticker():
    answer = deterministic_answer([snapshot(), snapshot("QQQ")], spec(tickers=["SPY", "QQQ"]))
    change = reading("Price change", 3)
    merge_history_section(answer, "SPY", "Price change: +3 USD", [change])
    section = next(s for s in answer["sections"] if s["name"] == "What changed")
    assert len(section["entries"]) == 2
    assert "Price change: +3 USD" in section["text"]
    assert change["id"] in section["fact_ids"]


async def test_model_history_inspection_replaces_the_missing_history_message(monkeypatch):
    from services.agent import research

    snap = snapshot()
    request = spec()
    answer = deterministic_answer([snap], request)
    change = reading("Price change since saved observation", 3)

    class Repository:
        async def progress(self, *_):
            return True

    class Model:
        calls = 0

        async def once(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"status": "ok", "name": "inspect_history", "data": {"ticker": "SPY"}}
            return {"status": "unavailable", "reason": "No further interpretation"}

    async def history(*_args, **_kwargs):
        return [change], "Compared with an earlier compatible observation"

    monkeypatch.setattr(research, "history_facts", history)
    service = research.ResearchService(Repository(), None, model=Model())
    await service._interpret("owner", "turn", request, answer, [snap])
    section = next(s for s in answer["sections"] if s["name"] == "What changed")
    assert "Price change: +3 USD" in section["text"]
    assert "No compatible earlier" not in section["text"]
    assert change["id"] in section["fact_ids"]
