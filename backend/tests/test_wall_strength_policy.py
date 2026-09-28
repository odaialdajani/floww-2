"""Strongest-wall identity checks: one deterministic winner or explicit ties."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.wall_strength import assign_strongest_wall  # noqa: E402


def test_single_mode_assigns_exactly_one_winner_on_ties():
    walls = [
        {"wall_id": "a", "adj_value": 10.0},
        {"wall_id": "b", "adj_value": -10.0},
        {"wall_id": "c", "adj_value": 10.0},
    ]
    out = assign_strongest_wall(walls, mode="single")
    assert out["status"] == "ok"
    assert [w["wall_id"] for w in out["winners"]] == ["a"]
    assert out["top"] == 10.0


def test_explicit_ties_mode_returns_every_top_wall():
    walls = [
        {"wall_id": "a", "adj_value": 10.0},
        {"wall_id": "b", "adj_value": -10.0},
        {"wall_id": "c", "adj_value": 9.0},
    ]
    out = assign_strongest_wall(walls, mode="explicit-ties")
    assert [w["wall_id"] for w in out["winners"]] == ["a", "b"]


def test_largest_cell_is_not_confused_with_largest_wall():
    walls = [
        {"wall_id": "single-spike", "adj_value": 100.0, "members": [100]},
        {"wall_id": "broad-wall", "adj_value": 90.0, "members": [101, 102, 103]},
    ]
    out = assign_strongest_wall(walls, mode="single")
    assert [w["wall_id"] for w in out["winners"]] == ["single-spike"]


def test_unknown_values_are_unavailable_not_zero():
    out = assign_strongest_wall(
        [{"wall_id": "a"}, {"wall_id": "b", "adj_value": None}], mode="single"
    )
    assert out == {"status": "unavailable", "reason": "NO_KNOWN_VALUES", "winners": []}
    with pytest.raises(ValueError):
        assign_strongest_wall([], mode="closest")
