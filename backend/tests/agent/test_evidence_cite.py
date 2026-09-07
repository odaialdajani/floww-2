"""Evidence cite-don't-type: deterministic ids, substitution, lint."""

from services.agent.evidence import ev_id, find_bare_numerals, substitute


def test_ev_ids_deterministic():
    a = ev_id("gex_profile", {"ticker": "SPY"}, "heatseeker", "2026-01-01")
    b = ev_id("gex_profile", {"ticker": "SPY"}, "heatseeker", "2026-01-01")
    assert a == b and a.startswith("ev")


def test_substitute_and_flag_unknown():
    ledger = {"ev12345678": {"value": 1500000, "status": "ok"}}
    text, flagged = substitute("GEX is {{ev12345678}} today.", ledger)
    assert "1.50M" in text and flagged == []
    text2, flagged2 = substitute("Wall at {{ev99999999}}.", ledger)
    assert flagged2 and "missing" in text2.lower()


def test_failed_entries_barred():
    ledger = {"ev12345678": {"value": 5, "status": "failed"}}
    text, flagged = substitute("Read {{ev12345678}}.", ledger)
    assert "unavailable" in text.lower() and flagged


def test_bare_numeral_lint():
    assert find_bare_numerals("There are 3 walls near 590.") != []
