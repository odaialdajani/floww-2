import pytest

from services.agent.explanations import explanation_menu, select_explanations


def sample(metric="Underlying price",status="stale",ticker="SPY",value=500):
    return dict(id=f"{ticker}:{metric}",metric=metric,ticker=ticker,horizon="all",value=value,
                status=status,event_time="2026-09-11T20:00:00+00:00",unit="USD")

def test_missing_flip_and_option_quote_are_explicit_without_inventing_values():
    facts=[sample()]
    menu={x["kind"]:x for x in explanation_menu(facts)}
    assert "cannot be placed above or below" in menu["missing_flip"]["text"]
    assert "underlying price is not an option premium" in menu["missing_option_quote"]["text"]
    assert "500" not in menu["missing_option_quote"]["text"]
    assert menu["missing_flip"]["fact_ids"]==[facts[0]["id"]]

def test_healthy_flip_does_not_allow_missing_or_stale_comparison_explanation():
    facts=[sample(status="ok"),sample("Displayed flip",status="ok",value=499)]
    kinds={x["kind"] for x in explanation_menu(facts)}
    assert not {"missing_flip","limited_comparison","no_current_readings"}&kinds
    facts[1]["status"]="degraded"
    assert "limited_comparison" in {x["kind"] for x in explanation_menu(facts)}

def test_gamma_definition_requires_gamma_evidence_and_keeps_unknown_time():
    facts=[sample("Total estimated gamma exposure",status="degraded",value=-50)]
    facts[0]["event_time"]=None
    gamma=next(x for x in explanation_menu(facts) if x["kind"]=="gamma_meaning")
    assert "assumed position signs" in gamma["text"] and "predict" in gamma["text"]
    assert select_explanations([gamma["id"]],facts)==[gamma]
    with pytest.raises(ValueError):select_explanations([gamma["id"]],[sample()])

def test_model_cannot_relabel_or_repeat_explanation_ids():
    menu=explanation_menu([sample(ticker="QQQ")])
    with pytest.raises(ValueError):select_explanations([menu[0]["id"]],[sample(ticker="SPY")])
    with pytest.raises(ValueError):select_explanations([menu[0]["id"]]*2,[sample(ticker="QQQ")])
    with pytest.raises(ValueError):select_explanations([{"text":"Guaranteed rise"}],[sample()])

def test_missing_history_and_volatility_are_not_asserted_when_the_facts_exist():
    facts=[sample("Price change since saved observation"),sample("Implied move"),sample("Realized volatility")]
    kinds={x["kind"] for x in explanation_menu(facts)}
    assert "missing_change" not in kinds and "missing_volatility" not in kinds


def test_stale_history_does_not_hide_a_healthy_current_comparison():
    current=sample(status="ok")
    flip=sample("Displayed flip",status="ok",value=499)
    old={**sample(),"id":"previous-price","event_time":"2026-09-10T20:00:00+00:00"}
    assert "limited_comparison" not in {x["kind"] for x in explanation_menu([current,flip,old])}
    flip["event_time"]="2026-09-11T19:30:00+00:00"
    assert "limited_comparison" in {x["kind"] for x in explanation_menu([current,flip,old])}


def test_group_local_missing_claim_prints_its_scope():
    price=sample(status="ok")
    flip=sample("Displayed flip",status="ok",value=499)
    other={**sample("Cached map price"),"horizon":"map:other"}
    missing=next(x for x in explanation_menu([price,flip,other]) if x["kind"]=="missing_flip")
    assert "map:other" in missing["text"]
