#!/usr/bin/env python3
"""GSD #11 gate — no silent exception handler without an inline justification.

A "silent handler" is an exception handler that BOTH

  1. catches broadly — a bare `except:`, `except Exception`, or
     `except BaseException` (alone, or as one member of a tuple). Note that
     `except BaseException` is strictly worse than `except Exception`: it also
     swallows `KeyboardInterrupt` and `SystemExit`.
  2. has a body that discards the exception entirely — exactly one statement,
     and that statement is `pass` or `...` (Ellipsis). The two are
     semantically identical here; `...` is not a loophole.

Swallowing an exception with no trace is only acceptable when the author
deliberately decided the failure is irrelevant to the caller — and said so, in a
comment, at the site.

A site is JUSTIFIED when a comment containing the marker `silent by design`
appears anywhere at the site — that is, on any line from the `except ...:` line
through the body line inclusive. The marker must be in a real COMMENT token: the
file is tokenized, so a string literal that merely contains the words does not
count. In practice the marker may sit on the `except` line, on the `pass` line,
or in the comment block immediately above the body.

Everything else is an offender.

Scope: backend/services/, backend/routes/, backend/server.py. Tests are exempt.

Usage (works from the repo root, from backend/, or from anywhere):
    python3 qc/audit/check_silent_excepts.py

Exit 0 = clean, exit 1 = at least one unjustified silent handler.

Tests: backend/tests/test_check_silent_excepts.py. That suite builds every
fixture with tmp_path, so it pins this gate's behaviour without depending on
live backend source.

This replaces an earlier grep/sed shell gate that never fired: GNU grep emits
`-A1` context lines as `file-LINENO-content` (dash), not `file:LINENO:content`
(colon), so the offender list was always empty and the gate always passed.
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from collections import defaultdict
from pathlib import Path

# Repo root is two levels up from qc/audit/ — independent of the cwd, so this
# runs identically from the repo root, from backend/, or from CI.
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"

# Directories scanned recursively, plus explicit single files.
SCAN_DIRS = [BACKEND / "services", BACKEND / "routes"]
SCAN_FILES = [BACKEND / "server.py"]

# Never scanned: tests are exempt by policy; venvs / caches are not our code.
EXCLUDE_PARTS = {".venv", ".venv313", "tests", "__pycache__", "node_modules"}

JUSTIFICATION_MARKER = "silent by design"

# ── Grandfathered sites (RATCHET — do not add to this list) ────────────────────
# The step this gate backs is named "no NEW silent except-pass". These two sites
# predate the gate ever actually running (its grep filter never matched, so it
# always exited 0) and were justified under the looser rule the workflow used to
# document: "either `# silent by design: <reason>` or a pre-existing explanatory
# comment on the same line". Both carry such a comment.
#
# The value is an EXACT ALLOWED COUNT, not a boolean. Keying on (path, source
# text) alone left a hole: a brand-new silent handler pasted into one of these
# files with the same trailing comment text was accepted for free. With a count,
# the (N+1)th occurrence of an allowlisted line is reported as an offender, so
# the list can only ratchet down — never absorb new debt.
#
# TODO(owner of backend/services): rewrite these two comments to carry the
# `silent by design:` marker and delete this list. It exists only because those
# files are outside the lane that installed this gate.
GRANDFATHERED: dict[tuple[str, str], int] = {
    ("backend/services/fill_monitor.py", "pass  # Metrics should never break fill recording"): 1,
    ("backend/services/gex_term_structure.py", "pass  # fall through to python implementation"): 1,
}

# Offender reasons, reported so the two failure modes are distinguishable.
REASON_UNJUSTIFIED = "unjustified"
REASON_OVER_BUDGET = "new occurrence of a grandfathered line (allowlist budget exceeded)"


def iter_target_files() -> list[Path]:
    """Every Python file in scope, de-duplicated and sorted."""
    seen: dict[Path, None] = {}
    for directory in SCAN_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            if EXCLUDE_PARTS.intersection(path.parts):
                continue
            seen[path] = None
    for path in SCAN_FILES:
        if path.is_file():
            seen[path] = None
    return list(seen)


def comment_lines(source: str) -> dict[int, str]:
    """Map line number -> comment text, using the real tokenizer.

    Tokenizing (rather than substring-matching the raw text) means a string
    literal that merely contains the marker cannot masquerade as a comment.
    """
    comments: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.string
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # A file that cannot be tokenized cannot be parsed either; the ast
        # pass below reports it.
        pass
    return comments


def catches_broad_exception(handler: ast.ExceptHandler) -> bool:
    """True for `except:`, `except Exception`, and `except BaseException`.

    Matches those names alone or as any member of an except tuple, and accepts a
    dotted form (`builtins.Exception`) as well.
    """
    if handler.type is None:
        return True  # bare `except:`

    broad = {"Exception", "BaseException"}

    def is_broad(node: ast.expr) -> bool:
        return (isinstance(node, ast.Name) and node.id in broad) or (
            isinstance(node, ast.Attribute) and node.attr in broad
        )

    if isinstance(handler.type, ast.Tuple):
        return any(is_broad(elt) for elt in handler.type.elts)
    return is_broad(handler.type)


def is_silent(handler: ast.ExceptHandler) -> bool:
    """True when the handler body is exactly one `pass` or one `...`."""
    if len(handler.body) != 1:
        return False
    stmt = handler.body[0]
    if isinstance(stmt, ast.Pass):
        return True
    # `...` parses as Expr(Constant(Ellipsis)) — same discard semantics as pass.
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    )


def check_file(
    path: Path,
    rel_path: str,
    grandfathered: dict[tuple[str, str], int] | None = None,
) -> list[tuple[int, str, str]]:
    """Return [(line_number, source_line, reason)] for offending silent handlers.

    `grandfathered` maps (rel_path, stripped source line) -> allowed count. The
    first N occurrences of a matching line are excused in line order; every
    occurrence beyond N is reported. Pass an explicit dict (including `{}`) to
    override the module-level allowlist — the tests rely on this.
    """
    allowlist = GRANDFATHERED if grandfathered is None else grandfathered
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    comments = comment_lines(source)
    lines = source.splitlines()

    # Every unjustified silent handler, before the allowlist is applied.
    candidates: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not catches_broad_exception(node) or not is_silent(node):
            continue

        body_line = node.body[0].lineno
        except_line = node.lineno
        # The whole handler site: `except ...:` line through the body line.
        window = range(min(except_line, body_line), body_line + 1)
        justified = any(JUSTIFICATION_MARKER in comments.get(ln, "").lower() for ln in window)
        if justified:
            continue
        src = lines[body_line - 1].strip() if body_line <= len(lines) else "pass"
        candidates.append((body_line, src))

    # Apply the allowlist by budget, oldest line first, so occurrence N+1 of an
    # allowlisted line is still reported.
    remaining: defaultdict[str, int] = defaultdict(int)
    for (a_rel, a_src), count in allowlist.items():
        if a_rel == rel_path:
            remaining[a_src] += count

    offenders: list[tuple[int, str, str]] = []
    for body_line, src in sorted(candidates):
        if remaining.get(src, 0) > 0:
            remaining[src] -= 1
            continue
        reason = REASON_OVER_BUDGET if (rel_path, src) in allowlist else REASON_UNJUSTIFIED
        offenders.append((body_line, src, reason))
    return offenders


def main() -> int:
    targets = iter_target_files()
    if not targets:
        print(f"ERROR: no Python files found under {BACKEND} - wrong repo root?")
        return 1

    offenders: list[tuple[str, int, str, str]] = []
    for path in targets:
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            for line_no, src, reason in check_file(path, rel):
                offenders.append((rel, line_no, src, reason))
        except SyntaxError as exc:
            print(f"{rel}:{exc.lineno}: SyntaxError - cannot audit ({exc.msg})")
            return 1

    if offenders:
        print("SILENT EXCEPT (unjustified) - add a `# silent by design: <reason>` comment:")
        for rel, line_no, src, reason in offenders:
            print(f"{rel}:{line_no}: {src}    [{reason}]")
        print(
            f"\n{len(offenders)} unjustified silent handler site(s) "
            f"across {len(targets)} scanned file(s)."
        )
        return 1

    print(
        f"OK - no unjustified silent except-pass sites "
        f"({len(targets)} files scanned under backend/services, backend/routes, backend/server.py)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
