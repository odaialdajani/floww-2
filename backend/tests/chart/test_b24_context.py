"""B24 context. Synthetic only."""
from services.chart_context import bind_context, resolve_context


def test_bind_and_race_guards():
    assert bind_context(focus=None, query="q", scope="s", cursor=1, generation=1)["status"] == "refused"
    d = bind_context(focus="SPY", query="q", scope="front", cursor=100, generation=7)
    assert d["status"] == "bound"
    assert resolve_context(d, {"generation": 6, "scope": "front"})["status"] == "refused"
    assert resolve_context(d, {"generation": 7, "scope": "other"})["status"] == "refused"
    assert resolve_context(d, {"generation": 7, "scope": "front", "pane_removed": True})["status"] == "refused"
    assert resolve_context(d, {"generation": 7, "scope": "front"})["status"] == "admitted"
