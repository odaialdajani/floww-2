"""Execute the mounted builder's restore decision against competing saved states."""
import ast
from pathlib import Path

import pytest

from services.wall_interaction import is_newer_state


def _select(memory, full, event):
    tree = ast.parse((Path(__file__).parents[2] / "server.py").read_text(encoding="utf-8"))
    builder = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_build_heatmap_impl")
    scope = {"mem_last": memory, "last": memory, "db_full": full, "db_last": event,
             "is_newer_state": is_newer_state}
    # Execute only the real restore decision, without starting unrelated feeds.
    for node in ast.walk(builder):
        if isinstance(node, ast.If) and isinstance(node.test, ast.BoolOp):
            first = node.test.values[0]
            if isinstance(first, ast.Name) and first.id in {"db_full", "db_last"}:
                # An elif is already executed as part of its owning if.
                if any(node in parent.orelse for parent in ast.walk(builder) if isinstance(parent, ast.If)):
                    continue
                exec(compile(ast.Module(body=[node], type_ignores=[]), "restore-decision", "exec"), scope)
    return scope["last"]


def _state(second, **extra):
    return {"at": f"2030-01-02T12:00:{second:02d}+00:00", **extra}


@pytest.mark.parametrize("memory,full,event,expected", [
    (None, _state(10), _state(20), _state(20)),
    (_state(30), _state(10), _state(20), _state(30)),
    (None, _state(20, inside_since="kept"), _state(20), _state(20, inside_since="kept")),
    (None, _state(25), _state(20), _state(25)),
])
def test_latest_observation_wins_without_losing_equal_time_dwell(memory, full, event, expected):
    assert _select(memory, full, event) == expected
