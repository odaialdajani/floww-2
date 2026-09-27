"""
Unit tests for the D-gate secret scanner (Agent D, D5/D7).
The scanner flags pasted secrets; the gate test scans the tree.

PATH NOTE: this file used to hardcode `/Users/nav/Documents/GitHub/floww`
(one developer's machine, a DIFFERENT repo from this one) for both the
sys.path insert and the tree scan. Two consequences:

  * The gate test passed while scanning a stale clone, so it never actually
    gated THIS repository's shipped code. It could not have caught a pasted
    credential committed here.
  * On CI, or in any worktree, that path does not exist at all.

Everything below is now derived from __file__, so the gate scans the tree it
actually ships in.
"""
from __future__ import annotations

import sys
from pathlib import Path

# backend/tests/chaos/ -> repo root is three parents up.
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"


def _ensure_imports():
    if "tests.chaos.secret_scan" not in sys.modules:
        sys.path.insert(0, str(BACKEND_ROOT))


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
    from tests.chaos.secret_scan import scan_tree

    # Scan THIS repo, not a hardcoded path on someone's machine.
    assert REPO_ROOT.is_dir(), f"repo root not found: {REPO_ROOT}"
    findings = []
    for sub in ("backend", "frontend", "scripts", ".github", "docs"):
        target = REPO_ROOT / sub
        if target.is_dir():
            findings += scan_tree(str(target))
    # Self-exclusion: the scanner's own test corpus holds fake vectors.
    findings = [f for f in findings if not f["path"].endswith("test_secret_scan.py")]
    assert findings == [], f"gate: pasted secrets in shipped code: {findings[:5]}"


def test_gate_scans_the_repo_it_ships_in():
    """Guard the guard: the scan root must be inside this repository.

    Deliberately does NOT assert a fixed directory name — a git worktree or a
    CI checkout can be called anything. What matters is that the path is
    derived from this file, so it can never point at some other clone the way
    the old hardcoded `/Users/nav/Documents/GitHub/floww` did.
    """
    here = Path(__file__).resolve()
    assert REPO_ROOT in here.parents, "scan root must be an ancestor of this test file"
    assert (REPO_ROOT / "backend" / "tests" / "chaos").is_dir(), (
        f"scan root {REPO_ROOT} does not look like this repo"
    )
    # The old bug: a path under a sibling repo, not this one.
    stale_clone = Path("/Users/nav/Documents/GitHub/floww")
    assert stale_clone != REPO_ROOT, "hardcoded sibling-clone path regressed"
