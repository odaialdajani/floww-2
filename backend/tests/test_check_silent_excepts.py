"""Tests for the GSD #11 silent-except gate (``qc/audit/check_silent_excepts.py``).

The gate runs in ``.github/workflows/lint.yml``. Its comment there claims this
suite exists; these tests are what makes that claim true.

Every fixture is built with ``tmp_path``. Nothing here reads live backend source,
so editing ``server.py`` / ``services/`` / ``routes/`` cannot break these tests —
only changing the gate's own behaviour can.
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

# ── Load the checker by path (it lives outside the backend package) ────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "qc" / "audit" / "check_silent_excepts.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_silent_excepts", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


# ── Helpers ───────────────────────────────────────────────────────────────────
def write(tmp_path: Path, source: str, name: str = "sample.py") -> Path:
    """Write a dedented Python source fixture and return its path."""
    path = tmp_path / name
    path.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    return path


def offenders(tmp_path: Path, source: str, rel_path: str = "backend/services/sample.py", **kw):
    """Run the gate over one fixture. `grandfathered={}` unless overridden."""
    kw.setdefault("grandfathered", {})
    return checker.check_file(write(tmp_path, source), rel_path, **kw)


def test_checker_script_exists():
    assert CHECKER_PATH.is_file(), f"gate script missing at {CHECKER_PATH}"


# ── FLAGGED: the core offence ─────────────────────────────────────────────────
def test_unjustified_except_exception_pass_is_flagged(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except Exception:
                pass
        """,
    )
    assert len(found) == 1
    line_no, src, reason = found[0]
    assert line_no == 5
    assert src == "pass"
    assert reason == checker.REASON_UNJUSTIFIED


def test_bare_except_pass_is_flagged(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except:
                pass
        """,
    )
    assert len(found) == 1


def test_exception_inside_a_tuple_is_flagged(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except (ValueError, Exception):
                pass
        """,
    )
    assert len(found) == 1


def test_dotted_exception_is_flagged(tmp_path):
    found = offenders(
        tmp_path,
        """
        import builtins

        def f():
            try:
                risky()
            except builtins.Exception:
                pass
        """,
    )
    assert len(found) == 1


# ── FLAGGED: DEFECT 4b — patterns the gate used to miss ───────────────────────
def test_except_baseexception_pass_is_flagged(tmp_path):
    """BaseException is strictly broader than Exception (eats KeyboardInterrupt)."""
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except BaseException:
                pass
        """,
    )
    assert len(found) == 1, "except BaseException: pass must not slip through"
    assert found[0][2] == checker.REASON_UNJUSTIFIED


def test_baseexception_inside_a_tuple_is_flagged(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except (KeyError, BaseException):
                pass
        """,
    )
    assert len(found) == 1


def test_ellipsis_body_is_flagged(tmp_path):
    """`...` discards the exception exactly like `pass`."""
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except Exception:
                ...
        """,
    )
    assert len(found) == 1, "an Ellipsis body must not be a loophole"
    assert found[0][1] == "..."


def test_baseexception_with_ellipsis_body_is_flagged(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except BaseException:
                ...
        """,
    )
    assert len(found) == 1


def test_ellipsis_body_can_be_justified(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except Exception:
                ...  # silent by design: best-effort metric emit
        """,
    )
    assert found == []


# ── PASSES: the justification marker ──────────────────────────────────────────
def test_marker_on_the_pass_line_justifies(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except Exception:
                pass  # silent by design: cache warm-up is best effort
        """,
    )
    assert found == []


def test_marker_on_the_except_line_justifies(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except Exception:  # silent by design: teardown must not raise
                pass
        """,
    )
    assert found == []


def test_marker_in_the_comment_block_above_the_pass_justifies(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except Exception:
                # silent by design: the caller already logged this path
                pass
        """,
    )
    assert found == []


def test_marker_is_case_insensitive(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except Exception:
                pass  # SILENT BY DESIGN: shutdown race
        """,
    )
    assert found == []


# ── A STRING LITERAL IS NOT A COMMENT ─────────────────────────────────────────
def test_string_literal_containing_the_marker_does_not_justify(tmp_path):
    """A naive raw-text substring scan would pass this file. It must not."""
    source = """
        NOTE = "silent by design: this is a string literal, not a comment"

        def f():
            try:
                risky()
            except Exception:
                pass
        """
    assert checker.JUSTIFICATION_MARKER in textwrap.dedent(source)
    found = offenders(tmp_path, source)
    assert len(found) == 1, "a string literal must never count as justification"


def test_comment_lines_ignores_string_literals():
    """Direct unit check on the tokenizer step behind the rule above."""
    source = 'X = "silent by design in a string"  # real comment here\n'
    comments = checker.comment_lines(source)
    assert comments == {1: "# real comment here"}
    assert checker.JUSTIFICATION_MARKER not in comments[1]


# ── NOT FLAGGED: out of scope by design ───────────────────────────────────────
def test_narrow_exception_with_pass_is_not_flagged(tmp_path):
    """The gate targets broad catches; `except ValueError: pass` is a choice."""
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except ValueError:
                pass
        """,
    )
    assert found == []


def test_handler_with_a_real_body_is_not_flagged(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except Exception:
                logger.exception("risky failed")
        """,
    )
    assert found == []


def test_multi_statement_body_ending_in_pass_is_not_flagged(tmp_path):
    found = offenders(
        tmp_path,
        """
        def f():
            try:
                risky()
            except Exception:
                logger.debug("ignored")
                pass
        """,
    )
    assert found == []


# ── DEFECT 4a — the grandfather list must ratchet, not absorb new debt ────────
GF_PATH = "backend/services/fill_monitor.py"
GF_LINE = "pass  # Metrics should never break fill recording"


def test_shipped_allowlist_is_count_keyed():
    """The allowlist must carry an integer budget, not a boolean membership."""
    assert isinstance(checker.GRANDFATHERED, dict)
    assert (GF_PATH, GF_LINE) in checker.GRANDFATHERED
    for key, budget in checker.GRANDFATHERED.items():
        assert isinstance(budget, int) and budget >= 1, key


def test_grandfathered_site_is_allowed_once(tmp_path):
    """One occurrence — the pre-existing debt — stays green."""
    found = checker.check_file(
        write(
            tmp_path,
            f"""
            def f():
                try:
                    risky()
                except Exception:
                    {GF_LINE}
            """,
        ),
        GF_PATH,
    )
    assert found == []


def test_second_occurrence_of_a_grandfathered_line_is_flagged(tmp_path):
    """THE HOLE: pasting the same excused line again used to be free.

    The old allowlist was keyed on (path, source text) with no count, so a
    brand-new silent handler carrying the same trailing comment was accepted.
    Budget-keying closes it: occurrence 2 is an offender.
    """
    found = checker.check_file(
        write(
            tmp_path,
            f"""
            def old():
                try:
                    risky()
                except Exception:
                    {GF_LINE}

            def brand_new():
                try:
                    risky()
                except Exception:
                    {GF_LINE}
            """,
        ),
        GF_PATH,
    )
    assert len(found) == 1, "a NEW copy of a grandfathered line must trip the gate"
    line_no, src, reason = found[0]
    assert src == GF_LINE
    assert reason == checker.REASON_OVER_BUDGET
    assert line_no == 11, "the LATER occurrence is the one reported"


def test_third_occurrence_reports_two_offenders(tmp_path):
    body = f"""
        def a():
            try:
                risky()
            except Exception:
                {GF_LINE}

        def b():
            try:
                risky()
            except Exception:
                {GF_LINE}

        def c():
            try:
                risky()
            except Exception:
                {GF_LINE}
        """
    found = checker.check_file(write(tmp_path, body), GF_PATH)
    assert len(found) == 2


def test_grandfathered_line_in_a_different_file_is_flagged(tmp_path):
    """The budget is per-path — it does not travel to another module."""
    found = checker.check_file(
        write(
            tmp_path,
            f"""
            def f():
                try:
                    risky()
                except Exception:
                    {GF_LINE}
            """,
        ),
        "backend/services/some_other_module.py",
    )
    assert len(found) == 1
    assert found[0][2] == checker.REASON_UNJUSTIFIED


def test_a_different_new_silent_pass_in_a_grandfathered_file_is_flagged(tmp_path):
    """Being on the list excuses ONE line, not the whole file."""
    found = checker.check_file(
        write(
            tmp_path,
            f"""
            def old():
                try:
                    risky()
                except Exception:
                    {GF_LINE}

            def brand_new():
                try:
                    risky()
                except Exception:
                    pass
            """,
        ),
        GF_PATH,
    )
    assert len(found) == 1
    assert found[0][1] == "pass"
    assert found[0][2] == checker.REASON_UNJUSTIFIED


# ── Scope policy ──────────────────────────────────────────────────────────────
def test_scan_never_includes_tests_or_venvs():
    """Structural check on the exemption policy (content-independent)."""
    for path in checker.iter_target_files():
        assert not checker.EXCLUDE_PARTS.intersection(path.parts), path


def test_syntax_error_is_surfaced_not_swallowed(tmp_path):
    """A file the gate cannot parse must raise, so main() can report and exit 1."""
    path = write(tmp_path, "def broken(:\n    pass\n")
    with pytest.raises(SyntaxError):
        checker.check_file(path, "backend/services/broken.py", grandfathered={})
