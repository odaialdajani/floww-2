"""Follow every local import reachable from the complete research boundary."""

import ast
from pathlib import Path

from services.agent.registry import BANNED_MODULE_SUBSTRINGS, BANNED_TOKEN_SUBSTRINGS

ROOT = Path(__file__).resolve().parents[2]


def local_source(module):
    base = ROOT.joinpath(*module.split("."))
    return next((p for p in (base.with_suffix(".py"), base / "__init__.py") if p.is_file()), None)


def test_research_transitively_avoids_order_modules_and_calls():
    pending = [
        "services.agent.tools",
        "services.agent.research",
        "services.agent.reads",
        "services.agent.model",
        "services.agent.repository",
        "services.research_data_seam",
    ]
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        assert not any(banned in name for banned in BANNED_MODULE_SUBSTRINGS), name
        path = local_source(name)
        if path is None:
            continue
        visited.add(name)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                pending.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    package = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
                    parts = package.split(".")
                    base = ".".join(parts[: len(parts) - node.level + 1] + ([base] if base else []))
                pending.append(base)
                pending.extend(base + "." + alias.name for alias in node.names)
            elif isinstance(node, ast.Call):
                called = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                assert called not in BANNED_TOKEN_SUBSTRINGS, f"{name}: {called}"
                assert called not in {"__import__", "import_module"}, f"Dynamic import needs explicit review: {name}"
    assert {
        "services.heatseeker",
        "services.agent.repository",
        "services.agent.contracts",
        "services.agent.spend",
    } <= visited
