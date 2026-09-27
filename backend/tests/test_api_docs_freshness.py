"""The generated API reference must stay true to the live app.

`docs/api/README.md` shipped with an empty Path column in all 159 rows and
`docs/api/openapi.json` held 156 paths against 369 real routes, with nothing
regenerating either. These tests pin both properties so the drift cannot
return quietly.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "docs" / "api"
README = API_DIR / "README.md"
SPEC = API_DIR / "openapi.json"
GENERATOR = REPO_ROOT / "qc" / "audit" / "generate_api_docs.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_api_docs", GENERATOR)
    assert spec and spec.loader, "generator must be importable"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generator_exists_and_is_runnable():
    assert GENERATOR.exists(), "the API docs have no regeneration path"


def test_readme_has_no_empty_path_cells():
    """The exact bug: every endpoint row rendered with a blank path."""
    text = README.read_text()
    empty_rows = re.findall(r"^\| (?:GET|POST|PUT|DELETE|PATCH) \|\s*\|", text, re.M)
    assert not empty_rows, f"{len(empty_rows)} endpoint rows have an empty Path cell"


def test_readme_is_marked_generated():
    text = README.read_text()
    assert "GENERATED FILE" in text, "README must say it is generated so nobody hand-edits it"
    assert "generate_api_docs.py" in text, "README must point at the regeneration command"


def test_spec_is_valid_json_with_paths():
    spec = json.loads(SPEC.read_text())
    assert spec.get("paths"), "spec must describe at least one path"
    for path in spec["paths"]:
        assert path.startswith("/"), f"path must be absolute: {path!r}"


def test_spec_and_readme_agree_on_path_count():
    """A path in the spec with no README row (or vice versa) is drift."""
    spec = json.loads(SPEC.read_text())
    spec_paths = set(spec["paths"])
    readme_paths = set(re.findall(r"^\| (?:GET|POST|PUT|DELETE|PATCH) \| `([^`]+)` \|", README.read_text(), re.M))
    assert spec_paths == readme_paths, (
        f"spec has {len(spec_paths - readme_paths)} paths absent from the README "
        f"and the README has {len(readme_paths - spec_paths)} absent from the spec"
    )


def test_grouping_splits_paths_sensibly():
    mod = _load_generator()
    assert mod._group_for("/api/heatseeker/gex") == "heatseeker"
    assert mod._group_for("/health") == "health"
    assert mod._group_for("/api/") == "(root)"
    # A version segment must not become the group name.
    assert mod._group_for("/api/v1/data/chain") == "data"
