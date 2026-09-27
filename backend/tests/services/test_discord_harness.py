"""G1.5: pure discord harness (cooldown/audit/NL-parse/fuzzy) — no discord.py."""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services import discord_harness as h  # noqa: E402


def test_parse_nl_maps_variants():
    assert h.parse_nl("spy gex") == ("heatmap", "SPY")
    assert h.parse_nl("qqq flip") == ("walls", "QQQ")
    assert h.parse_nl("SPY walls") == ("walls", "SPY")
    assert h.parse_nl("spy hm") == ("heatmap", "SPY")
    assert h.parse_nl("spy v") == ("vanna", "SPY")


def test_parse_nl_prefixless_ops_and_rejects():
    assert h.parse_nl("clock") == ("clock", None)
    assert h.parse_nl("Status") == ("status", None)
    assert h.parse_nl("buy 1 SPY") is None
    assert h.parse_nl("") is None
    assert h.parse_nl("hello world foo bar") is None


def test_cool_check_blocks_repeat_but_not_stranger():
    table, state = {"heatmap": 20.0}, {}
    assert h.cool_check(state, table, "u1", "heatmap", 1000.0) == (True, 0.0)
    ok, wait = h.cool_check(state, table, "u1", "heatmap", 1005.0)
    assert ok is False and wait > 0
    assert h.cool_check(state, table, "u2", "heatmap", 1005.0) == (True, 0.0)
    assert h.cool_check(state, table, "u1", "status", 1005.0) == (True, 0.0)


def test_audit_ring_counts_fold_variants():
    ring = collections.deque(maxlen=200)
    h.audit_append(ring, 7, "heatmap")
    h.audit_append(ring, 7, "heatmap SPY (nl)")
    h.audit_append(ring, 9, "walls")
    assert h.audit_counts(ring) == {"heatmap": 2, "walls": 1}


def test_fuzzy_hint_suggests_or_empty():
    known = ["heatmap", "walls", "vanna", "help"]
    assert "heatmap" in h.fuzzy_hint("heatma", known)
    assert h.fuzzy_hint("zzzqqq", known) == ""


def test_cooldown_line_summarizes_table():
    line = h.cooldown_line({"heatmap": 20.0, "vanna": 20.0, "walls": 5.0})
    assert "heatmap/vanna 20s" in line and "walls 5s" in line
