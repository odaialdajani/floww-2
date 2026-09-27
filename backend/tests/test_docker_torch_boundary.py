"""The production image excludes torch; this pins what that actually costs.

`Dockerfile.backend` strips torch to keep the image ~1GB smaller. Its comment
used to claim torch was "ONLY used by backend/tests/* (never imported by
server.py or any service at runtime)". That was false: five runtime modules
import it. They all guard the import, so production degrades rather than
crashes — but the false claim was the dangerous part, because it invited
someone to "fix" a guarded import by deleting the guard.

If a future change adds a MODULE-SCOPE torch import, the image will fail to
serve and this test fails with the file that did it.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DOCKERFILE = BACKEND.parent / "Dockerfile.backend"

# Runtime dirs only — tests legitimately import torch and are not shipped.
RUNTIME_DIRS = ["routes", "services", "scripts"]
RUNTIME_FILES = ["server.py", "data_collector.py", "cron_runner.py"]


def _module_scope_torch_imports() -> list[tuple[str, int]]:
    """Files importing torch at module scope (i.e. on `import service`)."""
    hits: list[tuple[str, int]] = []
    files: list[Path] = []
    for d in RUNTIME_DIRS:
        files.extend((BACKEND / d).rglob("*.py"))
    for f in RUNTIME_FILES:
        p = BACKEND / f
        if p.exists():
            files.append(p)

    for path in files:
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in tree.body:  # module scope only, not inside functions
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if m == "torch" or m.startswith("torch."):
                    hits.append((str(path.relative_to(BACKEND)), node.lineno))
    return hits


def test_production_image_has_no_module_scope_torch_import():
    """A module-scope import breaks the image, which ships without torch."""
    hits = _module_scope_torch_imports()
    assert not hits, (
        "module-scope torch import(s) would break the production image "
        f"(Dockerfile.backend strips torch): {hits}"
    )


def test_dockerfile_still_strips_torch():
    dockerfile = DOCKERFILE.read_text()
    assert "req.prod.txt" in dockerfile, "the torch-exclusion install step is gone"
    assert "req.prod.txt" in dockerfile and "pip install" in dockerfile


def test_dockerfile_comment_does_not_repeat_the_false_claim():
    """The specific lie that caused this whole problem must not come back."""
    text = DOCKERFILE.read_text()
    forbidden = [
        "ONLY used by backend/tests",
        "never imported by server.py or any",
        "zero runtime benefit",
    ]
    for phrase in forbidden:
        assert phrase not in text, f"stale/false claim reintroduced: {phrase!r}"
