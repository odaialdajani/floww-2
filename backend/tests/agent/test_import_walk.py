"""Static import-walk proof (plan v3 L1): tools/** never names a banned module."""

import ast
from pathlib import Path


def test_tools_transitively_avoid_banned_modules():
    from services.agent.registry import BANNED_MODULE_SUBSTRINGS

    root = Path(__file__).resolve().parents[2] / "services" / "agent" / "tools"
    assert root.exists(), f"tools dir missing: {root}"
    hits: list[str] = []
    for py in root.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                else:
                    mod = node.module or ""
                    names = [mod] + [a.name for a in node.names]
                blob = " ".join(names)
                for banned in BANNED_MODULE_SUBSTRINGS:
                    if banned in blob:
                        hits.append(f"{py.name}: {blob}")
    assert hits == [], f"banned imports in tools/: {hits[:5]}"


def test_tools_have_no_order_tokens():
    from services.agent.registry import BANNED_TOKEN_SUBSTRINGS

    root = Path(__file__).resolve().parents[2] / "services" / "agent" / "tools"
    hits: list[str] = []
    for py in root.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        for tok in BANNED_TOKEN_SUBSTRINGS:
            if tok in text:
                hits.append(f"{py.name}: {tok}")
    assert hits == [], f"order tokens in tools/: {hits[:5]}"
