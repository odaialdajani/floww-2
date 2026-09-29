"""Pins qc/audit/check_docs.py: internal doc links resolve and contract claims are backed by source.

A doc that links to a file not in the tree sends the reader nowhere and gives
no signal about whether they are on the wrong branch or the doc was never
written. A contract matrix that names producers which do not exist stops being
a contract. Both are silently wrong — the kind of thing this gate catches so
they never ship.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "qc" / "audit" / "check_docs.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_docs", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def test_gate_script_exists_and_is_importable():
    assert GATE.is_file()
    assert callable(gate.find_broken_links)
    assert callable(gate.find_unbacked_claims)
    assert callable(gate.main)


class TestBrokenLinks:
    def test_dependency_installs_are_never_scanned(self):
        """Vendored READMEs (nltk/openai dist-info links broke CI): .venv and
        node_modules contents depend on the installing environment, so the
        gate must not read them — otherwise green depends on which packages
        CI installed rather than on the tree."""
        docs = gate._markdown_files()
        bad = [str(p) for p in docs
               if ".venv" in p.parts or "node_modules" in p.parts]
        assert bad == [], f"gate scans dependency installs:\n{bad[:5]}"

    def test_template_files_are_excluded(self, tmp_path):
        """Templates with {{PLACEHOLDER}} links must not be flagged."""
        doc = tmp_path / "template_example.md"
        doc.write_text("[missing]({{PLACEHOLDER}})\n", encoding="utf-8")
        # find_broken_links only scans REPO_ROOT markdown globals; this test
        # confirms the exclusion logic at the unit level instead.
        assert gate._is_template(doc) is True

    def test_live_tree_has_no_broken_internal_links(self):
        broken = gate.find_broken_links()
        detail = "\n".join(
            f"  {b['doc']} -> {b['target']}" for b in broken
        )
        assert broken == [], f"broken internal doc links:\n{detail}"


class TestUnbackedClaims:
    def test_contract_matrix_is_fully_backed(self):
        claims = gate.find_unbacked_claims()
        detail = "\n".join(
            f"  {c['doc']}: {c['token']} ({c['reason']})" for c in claims
        )
        assert claims == [], f"unbacked contract claims:\n{detail}"


def test_main_exits_zero_on_a_clean_tree():
    assert gate.main([]) == 0
