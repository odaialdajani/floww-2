#!/usr/bin/env python3
"""Dead-wire gate — every local `from X import Y` must resolve to a real name.

WHY THIS EXISTS
===============
A dead wire is an import of a symbol that does not exist. On its own that
raises ImportError at the point of import, which is loud. The dangerous
shape is when the import sits inside a `try` whose handler swallows
everything: the error is caught, the feature silently degrades to "no data",
and the code LOOKS honest while being dead.

The canonical instance: a session-VWAP helper imported
`public_api.fetch_public_bars`, which does not exist. The broad `except`
turned that into a permanent `NO_BARS`, so the VWAP line never rendered and
nothing anywhere reported a failure. It is indistinguishable from "there was
no data" unless something checks that the symbol resolves.

This gate checks that every `ImportFrom` naming a LOCAL module resolves, by
parsing the target module rather than importing it (no side effects, no
dependency on the runtime environment).

Scope: backend production code (server.py, services/, routes/, domain/).
Tests are exempt — they legitimately build fake modules.

Usage:
    python3 qc/audit/find_dead_imports.py          # exit 1 if any dead wire
    python3 qc/audit/find_dead_imports.py --json   # machine-readable

Exit 0 = every local import resolves, exit 1 = at least one does not.

Tests: backend/tests/test_dead_import_gate.py, which builds its fixtures in
tmp_path so this gate is pinned without depending on live backend source.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"

SCAN_ROOTS = [BACKEND / "services", BACKEND / "routes", BACKEND / "domain"]
SCAN_FILES = [BACKEND / "server.py"]

# Local module prefixes. Anything else (scipy, httpx, decoder_core, ...) is
# not this repo's business.
LOCAL_PREFIXES = ("services", "routes", "domain", "utils", "handlers", "models")


def _top_level_names(tree: ast.Module) -> set[str]:
    """Every name the module binds at top level.

    Deliberately over-inclusive: names bound inside `try`/`except ImportError`
    guards and `if TYPE_CHECKING` blocks are real for at least one
    configuration, and missing one would produce a false positive.
    """
    names: set[str] = set()

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(child.name)
                continue
            if isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
                    elif isinstance(target, ast.Tuple):
                        names.update(e.id for e in target.elts if isinstance(e, ast.Name))
                continue
            if isinstance(child, ast.Import):
                for alias in child.names:
                    names.add(alias.asname or alias.name.split(".")[0])
                continue
            if isinstance(child, ast.ImportFrom):
                for alias in child.names:
                    names.add(alias.asname or alias.name)
                continue
            if isinstance(child, (ast.Try, ast.If, ast.With, ast.For, ast.While)):
                visit(child)

    visit(tree)
    return names


def _module_file(module: str) -> Path | None:
    """Resolve a local module name to a file, or a package __init__."""
    parts = module.split(".")
    if parts[0] not in LOCAL_PREFIXES:
        return None
    candidate = BACKEND.joinpath(*parts)
    if candidate.with_suffix(".py").is_file():
        return candidate.with_suffix(".py")
    if (candidate / "__init__.py").is_file():
        return candidate / "__init__.py"
    return None


def _submodule_exists(module: str, name: str) -> bool:
    """True when `name` is a real submodule of a local package."""
    candidate = BACKEND.joinpath(*module.split("."), name)
    return candidate.with_suffix(".py").is_file() or (candidate / "__init__.py").is_file()


def collect_symbols() -> dict[str, set[str]]:
    table: dict[str, set[str]] = {}
    roots = SCAN_ROOTS + [BACKEND / p for p in ("utils", "handlers", "models")]
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = path.relative_to(BACKEND)
            parts = rel.parts[:-1] if rel.name == "__init__.py" else rel.parts[:-1] + (rel.stem,)
            table[".".join(parts)] = _top_level_names(tree)
    return table


def _display(path: Path) -> str:
    """Path relative to the repo when it is inside it, else absolute.

    A fixture built in tmp_path is outside the repo, so a bare
    `relative_to(REPO_ROOT)` raises and takes the whole gate down.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def find_dead_imports() -> list[dict[str, object]]:
    table = collect_symbols()
    files: list[Path] = [p for p in SCAN_FILES if p.is_file()]
    for root in SCAN_ROOTS:
        if root.is_dir():
            files.extend(sorted(root.rglob("*.py")))

    dead: list[dict[str, object]] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            module = node.module
            if module.split(".")[0] not in LOCAL_PREFIXES:
                continue
            target_file = _module_file(module)
            if target_file is None:
                dead.append({
                    "file": _display(path),
                    "line": node.lineno,
                    "module": module,
                    "name": None,
                    "reason": "MODULE_NOT_FOUND",
                })
                continue
            known = table.get(module)
            if known is None:
                try:
                    known = _top_level_names(ast.parse(target_file.read_text(encoding="utf-8")))
                except (SyntaxError, UnicodeDecodeError):
                    continue
            for alias in node.names:
                if alias.name == "*" or alias.name in known:
                    continue
                if _submodule_exists(module, alias.name):
                    continue
                dead.append({
                    "file": _display(path),
                    "line": node.lineno,
                    "module": module,
                    "name": alias.name,
                    "reason": "SYMBOL_NOT_FOUND",
                })
    return sorted(dead, key=lambda d: (str(d["file"]), int(d["line"])))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="dead-wire gate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    dead = find_dead_imports()
    if args.json:
        print(json.dumps(dead, indent=2))
    elif not dead:
        print("OK — every local import resolves to a real symbol")
    else:
        print(f"DEAD WIRES: {len(dead)}")
        for item in dead:
            print(f"  {item['file']}:{item['line']}  {item['module']}.{item['name']}  ({item['reason']})")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())


