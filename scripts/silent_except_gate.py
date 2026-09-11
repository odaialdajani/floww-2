"""Silent-except gate: fail on bare `except:` or handlers whose body is only `pass`.

Usage:
    python scripts/silent_except_gate.py [--root backend] [--allowlist <substr> ...]

Exit 1 on any hit, printing `file:line` per violation. `--allowlist` accepts
zero or more path substrings; matching files are skipped.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path


def _is_silent(body: list[ast.stmt]) -> bool:
    stmts = [s for s in body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    return bool(stmts) and all(isinstance(s, ast.Pass) for s in stmts)


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.hits: list[str] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        bare = node.type is None
        silent = _is_silent(node.body)
        if bare or silent:
            kind = "bare-except" if bare else "silent-except-pass"
            self.hits.append(f"{self.path}:{node.lineno} {kind}")
        self.generic_visit(node)


def scan(root: Path, allowlist: list[str]) -> list[str]:
    hits: list[str] = []
    for py in sorted(root.rglob("*.py")):
        s = str(py)
        if any(a in s for a in allowlist):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=s)
        except (SyntaxError, UnicodeDecodeError):
            continue
        v = _Visitor(py)
        v.visit(tree)
        hits.extend(v.hits)
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fail on silent except handlers.")
    ap.add_argument("--root", default="backend", help="Directory tree to scan")
    ap.add_argument(
        "--allowlist",
        nargs="*",
        default=[],
        help="Path substrings to skip (e.g. vendor files)",
    )
    args = ap.parse_args(argv)
    hits = scan(Path(args.root), args.allowlist)
    for h in hits:
        print(h)
    if hits:
        print(f"silent-except gate: {len(hits)} violation(s)", file=sys.stderr)
        return 1
    print("silent-except gate: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
