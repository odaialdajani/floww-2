"""
Unit tests for the D-gate secret scanner (Agent D, D5/D7).
The scanner flags pasted secrets; the gate test scans the tree.
"""
from __future__ import annotations

import sys


def _ensure_imports():
    if "tests.chaos.secret_scan" not in sys.modules:
        sys.path.insert(0, "/Users/nav/Documents/GitHub/floww/backend")


_ensure_imports()

from tests.chaos.secret_scan import scan_text


def test_flags_live_keys():
    assert scan_text('client = db.Live(key="db-abc123XYZ456")')
    assert scan_text('api_key = "sk-live-abcdefghij1234567890"')
    assert scan_text("ghp_abcdefghijklmnopqrstuvwxyz012345")
    assert scan_text("AKIAIOSFODNN7QW4ERTY")
    assert scan_text("-----BEGIN RSA PRIVATE KEY-----")


def test_ignores_placeholders_and_tests():
    assert scan_text('api_key = os.environ.get("PUBLIC_API_KEY", "")') == []
    assert scan_text('key = "<REDACTED>"') == []
    assert scan_text('key = "test-key-for-unit-tests-only"') == []
    assert scan_text("# example: sk-...") == []
    assert scan_text('key = "sk-test"') == []
    assert scan_text("") == []


def test_regression_prose_and_enums_ignored_live_substrings_flagged():
    assert scan_text("db-exception-yields-empty") == []  # hyphenated prose
    assert scan_text('token = "TREND_STRONG_UP"') == []  # enum constant
    assert scan_text('client = db.Live(key="db-PBRQ7ia8dQ8wi6Yj7imWDfxXxGFrN")')  # xxx inside live key


def test_gate_shipped_tree_clean():
    import os

    from tests.chaos.secret_scan import scan_tree

    root = "/Users/nav/Documents/GitHub/floww"
    findings = []
    for sub in ("backend", "frontend", "scripts"):
        findings += scan_tree(os.path.join(root, sub))
    # Self-exclusion: the scanner's own test corpus holds fake vectors.
    findings = [f for f in findings if not f["path"].endswith("test_secret_scan.py")]
    assert findings == [], f"gate: pasted secrets in shipped code: {findings[:5]}"
