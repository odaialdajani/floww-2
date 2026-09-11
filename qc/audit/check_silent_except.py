#!/usr/bin/env python3
"""AST gate: no unjustified silent except-pass (P1, replaces grep gate GSD #11).

A handler is *silent* when its body is only ``pass`` / ``...`` (a
docstring Expr is ignored). A silent handler is *justified* only when a
comment containing ``silent by design`` (case-insensitive) appears on any
line from the ``except`` line through the end of the handler body.

Unlike the old grep check, this catches bare ``except:``, typed handlers
(``except ValueError:``), tuples/aliases (``except (A, B):``), ``as``
targets, same-line bodies (``except X: pass``), nested scopes, and
pass-after-comment layouts, and it is not fooled by the words
``except ... pass`` inside strings or comments.

Modes:
  full-tree  (no --baseline): exit 1 if any unjustified silent handler.
  ratchet    (--baseline FILE): only findings whose key is absent from FILE
             fail. Freeze with --freeze-baseline FILE.
  Malformed input (missing file, syntax error) exits 2 -- it is never a
  silent pass.

Finding keys are ``relpath:scope:clause#n`` (nth silent handler with that
stem in the file, in AST walk order) so line shifts do not create
false NEW findings, while a genuinely added handler always fails. Test files (*/tests/*, test_*, *_test.py, conftest.py)
are skipped, matching the previous gate's test exemption.
"""

import argparse
import ast
import io
import sys
import tokenize
from pathlib import Path

MARKER = "silent by design"
EXIT_OK = 0
EXIT_OFFENDERS = 1
EXIT_MALFORMED = 2

SKIP_DIRS = {"tests", "__pycache__"}


def is_test_path(path: Path) -> bool:
    if path.name == "conftest.py":
        return True
    if path.name.startswith("test_") or path.name.endswith("_test.py"):
        return True
    return any(part in SKIP_DIRS for part in path.parts)


def file_comments(source: str) -> dict:
    comments: dict = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                comments.setdefault(tok.start[0], []).append(tok.string)
    except (tokenize.TokenError, SyntaxError, IndentationError):
        pass
    return comments


def scope_name(node: ast.ExceptHandler, tree: ast.AST) -> str:
    """Innermost enclosing function/class, or <module>."""
    best = "<module>"

    def visit(current: ast.AST, name: str) -> None:
        nonlocal best
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                child_name = f"{name}.{child.name}" if name != "<module>" else child.name
                if node in set(ast.walk(child)):
                    best = child_name
                    visit(child, child_name)
            else:
                if node in set(ast.walk(child)):
                    visit(child, name)

    visit(tree, "<module>")
    return best


def clause_text(node: ast.ExceptHandler) -> str:
    if node.type is None:
        return "bare"
    try:
        return ast.unparse(node.type).strip()
    except Exception:
        return ast.dump(node.type)


def is_silent(body: list) -> bool:
    code = [
        s
        for s in body
        if not (
            isinstance(s, ast.Expr)
            and isinstance(s.value, ast.Constant)
            and isinstance(s.value.value, str)
        )
    ]
    if not code:
        return False
    return all(
        isinstance(s, ast.Pass)
        or (
            isinstance(s, ast.Expr)
            and isinstance(s.value, ast.Constant)
            and s.value.value is Ellipsis
        )
        for s in code
    )


def check_file(path: Path, root: Path) -> tuple:
    """Return (findings, errors). Findings are (key, display) for unjustified silent handlers."""
    try:
        source = path.read_text()
    except OSError as exc:
        return [], [f"{path}: unreadable: {exc}"]
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [], [f"{path}: syntax error: {exc}"]
    comments = file_comments(source)
    findings = []
    seen: dict = {}
    rel = path.relative_to(root).as_posix() if path.is_absolute() else path.as_posix()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not is_silent(node.body):
            continue
        end = getattr(node.body[-1], "end_lineno", node.lineno) or node.lineno
        blob = " ".join(
            c for ln in range(node.lineno, end + 1) for c in comments.get(ln, [])
        )
        if MARKER in blob.lower():
            continue
        stem = f"{rel}:{scope_name(node, tree)}:{clause_text(node)}"
        seen[stem] = seen.get(stem, 0) + 1
        key = f"{stem}#{seen[stem]}"
        findings.append((key, f"{rel}:{node.lineno} ({clause_text(node)})"))
    return findings, []


def collect(targets: list, root: Path) -> tuple:
    findings: list = []
    errors: list = []
    files: list = []
    for target in targets:
        p = Path(target)
        if not p.is_absolute():
            p = root / p
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.is_file():
            files.append(p)
        else:
            errors.append(f"{target}: no such file or directory")
    for path in files:
        if is_test_path(path):
            continue
        f, e = check_file(path, root)
        findings.extend(f)
        errors.extend(e)
    return findings, errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AST gate for unjustified silent except-pass.")
    parser.add_argument("targets", nargs="*", default=["services", "routes", "server.py"])
    parser.add_argument("--root", default=".", help="root for targets and relative keys")
    parser.add_argument("--baseline", default=None, help="ratchet file; only NEW keys fail")
    parser.add_argument("--freeze-baseline", default=None, help="write all finding keys and exit 0/2")
    args = parser.parse_args(argv)

    root = Path(args.root)
    findings, errors = collect(args.targets, root)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return EXIT_MALFORMED

    if args.freeze_baseline:
        out = Path(args.freeze_baseline)
        out.write_text("".join(k + "\n" for k, _ in sorted(findings)))
        print(f"froze {len(findings)} findings -> {out}")
        return EXIT_OK

    if args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.is_file():
            print(f"ERROR: baseline not found: {baseline_path}", file=sys.stderr)
            return EXIT_MALFORMED
        known = {ln.strip() for ln in baseline_path.read_text().splitlines() if ln.strip()}
        new = [(k, d) for k, d in findings if k not in known]
        if new:
            for _, display in sorted(new, key=lambda x: x[1]):
                print(f"SILENT EXCEPT (new, unjustified): {display}")
            print(f"{len(new)} new unjustified silent handler(s); baseline holds {len(known)}.")
            return EXIT_OFFENDERS
        print(f"OK: {len(findings)} silent handler(s), all in baseline ({len(known)}).")
        return EXIT_OK

    if findings:
        for _, display in sorted(findings, key=lambda x: x[1]):
            print(f"SILENT EXCEPT (unjustified): {display}")
        return EXIT_OFFENDERS
    print("OK: no unjustified silent handlers.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
