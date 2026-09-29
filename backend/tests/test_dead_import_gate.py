"""Pins qc/audit/find_dead_imports.py, and asserts the live tree has no dead wires.

The gate exists because a `from X import Y` naming a symbol that does not
exist is INVISIBLE when it sits inside a broad `except`: the feature degrades
to "no data" forever and nothing reports a failure. That is exactly how a
session-VWAP line stayed permanently absent while looking honest.

These tests build their fixtures in tmp_path, so the gate's behaviour is
pinned without depending on live backend source. The final test runs the gate
against the real tree, which is the standing assertion.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "qc" / "audit" / "find_dead_imports.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("find_dead_imports", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def test_gate_script_exists_and_is_importable():
    assert GATE.is_file()
    assert callable(gate.main)
    assert callable(gate.find_dead_imports)


class TestSymbolCollection:
    def test_collects_functions_classes_and_assignments(self):
        tree = ast.parse(
            "import os\n"
            "from json import loads\n"
            "X = 1\n"
            "A, B = 2, 3\n"
            "class C: pass\n"
            "def f(): pass\n"
            "async def g(): pass\n"
        )
        names = gate._top_level_names(tree)
        assert {"os", "loads", "X", "A", "B", "C", "f", "g"} <= names

    def test_collects_names_bound_inside_import_guards(self):
        """A name defined only in a try/except ImportError block is real for
        at least one configuration, so it must not be reported as missing."""
        tree = ast.parse(
            "try:\n"
            "    from numba import njit\n"
            "except ImportError:\n"
            "    njit = None\n"
        )
        names = gate._top_level_names(tree)
        assert "njit" in names

    def test_collects_names_bound_inside_type_checking_blocks(self):
        tree = ast.parse(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from collections import OrderedDict\n"
        )
        assert "OrderedDict" in gate._top_level_names(tree)


class TestResolution:
    def test_non_local_modules_are_out_of_scope(self):
        assert gate._module_file("scipy.stats") is None
        assert gate._module_file("httpx") is None
        assert gate._module_file("decoder_core") is None

    def test_local_module_resolves_to_a_file(self):
        resolved = gate._module_file("domain.exposure_metrics")
        assert resolved is not None and resolved.name == "exposure_metrics.py"

    def test_missing_local_module_resolves_to_none(self):
        assert gate._module_file("services.does_not_exist_anywhere") is None


class TestLiveTree:
    def test_every_local_import_in_production_code_resolves(self):
        """THE standing assertion. A new dead wire fails this test."""
        dead = gate.find_dead_imports()
        detail = "\n".join(
            f"  {d['file']}:{d['line']} {d['module']}.{d['name']} ({d['reason']})"
            for d in dead
        )
        assert dead == [], (
            "dead wires found — a name is imported that does not exist. If the "
            "import is inside a broad except, the feature is silently dead:\n" + detail
        )

    def test_gate_reports_a_dead_wire_it_is_given(self, tmp_path, monkeypatch):
        """The gate must actually fire, or the standing assertion proves nothing."""
        services = tmp_path / "services"
        services.mkdir()
        (services / "real.py").write_text("def present(): pass\n", encoding="utf-8")
        (services / "caller.py").write_text(
            "try:\n"
            "    from services.real import absent_symbol\n"
            "except Exception:\n"
            "    absent_symbol = None\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(gate, "BACKEND", tmp_path)
        monkeypatch.setattr(gate, "SCAN_ROOTS", [services])
        monkeypatch.setattr(gate, "SCAN_FILES", [])
        dead = gate.find_dead_imports()
        assert len(dead) == 1
        assert dead[0]["name"] == "absent_symbol"
        assert dead[0]["reason"] == "SYMBOL_NOT_FOUND"

    @pytest.mark.parametrize("argv", [["--json"]])
    def test_json_mode_is_machine_readable(self, argv, capsys):
        gate.main(argv)
        import json

        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)


def test_backend_dir_is_where_we_think_it_is():
    assert (REPO_ROOT / "backend" / "server.py").is_file()
    assert sys.version_info >= (3, 11)
