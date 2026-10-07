"""R15 boundary: new lifecycle/producer/fetch/route modules carry no ambient
network capability. All broker/HTTP access is injected (tests) or arrives via
the existing gated route / adapter seam — never constructed here."""

import ast
import os
import pathlib
import sys

sys.path.insert(0, "backend")

MODULES = [
    "backend/services/public_execution_lifecycle.py",
    "backend/services/solstice_price_producer.py",
    "backend/services/solstice_price_fetch.py",
    "backend/routes/solstice_price_paths.py",
]

# Resolve from the test file location, not CWD: the suite runs both from the
# worktree root and from backend/ (historical CWD path-artifact trap).
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _mod(rel: str) -> pathlib.Path:
    return REPO_ROOT / rel

FORBIDDEN_TOP_LEVEL = {
    "httpx", "requests", "urllib", "urllib3", "socket", "aiohttp",
    "public_api",  # services.public_api (PublicBroker) must never be imported here
}

FORBIDDEN_CONSTRUCT = ["PublicBroker(", "AsyncClient(", "urlopen("]


def _top_imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.name or "").split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names.add(mod.split(".")[0])
            for a in node.names:
                names.add((a.name or "").split(".")[0])
    return names


def test_no_ambient_network_imports():
    offenders: dict[str, set[str]] = {}
    for rel in MODULES:
        p = _mod(rel)
        assert p.exists(), f"missing module under test: {rel}"
        hits = _top_imports(p) & FORBIDDEN_TOP_LEVEL
        # `public_api_adapter` (data-only) is allowed; `public_api` (broker) is not.
        hits.discard("public_api_adapter")
        if hits:
            offenders[rel] = hits
    assert not offenders, f"ambient network imports: {offenders}"


def test_no_direct_broker_or_http_construction():
    offenders: dict[str, list[str]] = {}
    for rel in MODULES:
        src = _mod(rel).read_text()
        hits = [t for t in FORBIDDEN_CONSTRUCT if t in src]
        if hits:
            offenders[rel] = hits
    assert not offenders, f"direct broker/HTTP construction: {offenders}"


def test_fetch_seam_uses_adapter_inside_function_only():
    import services.solstice_price_fetch as fetch_mod

    assert not hasattr(fetch_mod, "PublicBroker")
    assert not hasattr(fetch_mod, "httpx")
    src = _mod("backend/services/solstice_price_fetch.py").read_text()
    assert "fetch_quotes_from_public_api" in src  # declared adapter scope
    assert "place_order" not in src
    assert "cancel_order" not in src


def test_lifecycle_never_reads_venue_flag():
    src = _mod("backend/services/public_execution_lifecycle.py").read_text()
    # Arming stays with the caller: no environment reads anywhere in the module
    # (the flag name appears only in prose in the docstring, never in code).
    assert "os.environ" not in src
    assert "os.getenv" not in src
    assert "getenv" not in src



def _production_python(root: pathlib.Path):
    """Walk project callers without entering installed Python environments."""
    for folder, directories, files in os.walk(root):
        current = pathlib.Path(folder)
        directories[:] = sorted(name for name in directories
                               if name != "tests" and not (current / name / "pyvenv.cfg").is_file())
        for name in sorted(files):
            if name.endswith(".py") and "test_" not in name:
                yield current / name

def test_no_production_callers_of_lifecycle_transitions():
    """Fail-closed approval stance, pinned: no route/service/caller in the tree
    reaches a lifecycle transition, so no unapproved path exists. The day a
    production caller is added, this test names it and the commissioning
    contract (require_approval=True + venue gate) must cover it."""
    import re

    hits: dict[str, list[str]] = {}
    for path in _production_python(REPO_ROOT / "backend"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel or "test_" in path.name:
            continue
        if rel in ("backend/services/public_execution_lifecycle.py",):
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        found = re.findall(
            r"(?:lifecycle|execution_lifecycle|lc)\s*\.\s*"
            r"(submit|reconcile(?:_all)?|cancel|supersede|preflight)\s*\(",
            src,
        )
        if found:
            hits[rel] = sorted(set(found))
    assert not hits, f"production lifecycle callers (need approval-desk cover): {hits}"


def test_scanner_excludes_installed_python_envs(tmp_path, monkeypatch):
    module = sys.modules[__name__]
    env = tmp_path / "backend" / ".venv313"
    env.mkdir(parents=True)
    (env / "pyvenv.cfg").write_text("home = fixture-python\n", encoding="utf-8")
    (env / "third_party.py").write_text("lc.submit()\n", encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    test_no_production_callers_of_lifecycle_transitions()


def test_scanner_excludes_nested_test_helpers(tmp_path, monkeypatch):
    module = sys.modules[__name__]
    folder = tmp_path / "backend" / "tests"
    folder.mkdir(parents=True)
    (folder / "helper.py").write_text("lc.cancel()\n", encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    test_no_production_callers_of_lifecycle_transitions()


def test_scanner_still_names_adjacent_source_callers(tmp_path, monkeypatch):
    import pytest
    module = sys.modules[__name__]
    env = tmp_path / "backend" / "installed-env"
    env.mkdir(parents=True)
    (env / "pyvenv.cfg").write_text("home = fixture-python\n", encoding="utf-8")
    project = tmp_path / "backend" / "ordinary-source"
    project.mkdir()
    (project / "caller.py").write_text("lc.submit()\n", encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    with pytest.raises(AssertionError, match="ordinary-source.*caller"):
        test_no_production_callers_of_lifecycle_transitions()
