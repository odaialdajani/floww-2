#!/usr/bin/env python3
"""Regenerate docs/api/openapi.json + docs/api/README.md from the live app.

WHY THIS EXISTS
---------------
Both artifacts were hand-maintained and drifted silently:

  * `docs/api/README.md` listed all 159 endpoints with an EMPTY Path column
    in every row. The file claims to be an API reference and cannot be used
    to call anything.
  * `docs/api/openapi.json` held 156 paths while the app really exposes 369
    routes, and no workflow or script ever regenerated it.

So the spec was not a description of the API; it was a stale guess at one.
This script makes the app the single source of truth.

It imports `server.app` and dumps `app.openapi()`, so a route that fails to
import cannot be silently omitted from the docs -- it fails the run instead.

USAGE
-----
    python3 qc/audit/generate_api_docs.py            # rewrite both files
    python3 qc/audit/generate_api_docs.py --check    # CI: fail if stale

`--check` is the mode worth wiring into a workflow: it exits 1 and prints a
diff-able message when the committed files no longer match the app, which is
the failure that went unnoticed for so long.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
API_DIR = REPO_ROOT / "docs" / "api"
SPEC_PATH = API_DIR / "openapi.json"
README_PATH = API_DIR / "README.md"

# Group the reference by the module-ish segment after /api, so the README
# reads like a table of contents instead of one 369-row wall.
GROUPING_SKIP = {"api", "v1"}


def _group_for(path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p]
    parts = [p for p in parts if p not in GROUPING_SKIP]
    if not parts:
        return "(root)"
    if parts[0] in {"health", "metrics"}:
        return parts[0]
    # Collapse a leading version-ish or id-ish segment into the group name.
    return parts[0].strip("{}") or "(root)"


def _load_spec() -> dict:
    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    # server.py mounts a lot at import time and logs warnings for optional
    # deps. Those are expected here; we only care that the app object builds.
    from server import app  # noqa: PLC0415

    # DETERMINISM. server.py registers the root health probe as both
    # @app.get("/") and @app.head("/"). FastAPI derives operationId from
    # name+path+method, and when two routes collide it emits a
    # "Duplicate Operation ID" warning and the winner is decided by
    # dict/set iteration order -- which varies between interpreter runs
    # because the route table is built from a set. Left alone, that made
    # this script's own --check gate flip between pass and fail on
    # identical source, roughly 1 run in 3, which would have made CI a
    # coin toss.
    #
    # Fix: give every operation a stable, explicitly-computed id instead of
    # the colliding generated one. Ids stay unique because the method is
    # part of the key, and they no longer depend on registration order.
    spec = app.openapi()
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            slug = path.strip("/").replace("/", "_").replace("{", "").replace("}", "") or "root"
            op["operationId"] = f"{method.lower()}_{slug}"
    return spec


def render_readme(spec: dict) -> str:
    paths = spec.get("paths", {})
    groups: dict[str, list[tuple[str, str, str]]] = {}
    total = 0
    for path, ops in paths.items():
        for method, op in ops.items():
            if method.lower() not in {"get", "post", "put", "delete", "patch", "head", "options"}:
                continue
            summary = (op.get("summary") or op.get("description") or "").strip()
            summary = summary.split("\n")[0][:80]
            groups.setdefault(_group_for(path), []).append((method.upper(), path, summary))
            total += 1

    out = [
        "# API Reference",
        "",
        "<!-- GENERATED FILE - DO NOT EDIT BY HAND. -->",
        "<!-- Regenerate: python3 qc/audit/generate_api_docs.py -->",
        "<!-- Verify:     python3 qc/audit/generate_api_docs.py --check -->",
        "",
        f"Total endpoints: {total}",
        f"Route groups: {len(groups)}",
        "",
        "Generated from the live FastAPI app, so every path below is a real,",
        "callable route rather than a hand-copied guess.",
        "",
    ]
    for name in sorted(groups):
        rows = sorted(groups[name], key=lambda r: (r[1], r[0]))
        out.append(f"## {name} ({len(rows)} endpoints)")
        out.append("")
        out.append("| Method | Path | Summary |")
        out.append("|--------|------|---------|")
        for method, path, summary in rows:
            out.append(f"| {method} | `{path}` | {summary} |")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if committed files are stale")
    args = ap.parse_args()

    spec = _load_spec()
    spec_text = json.dumps(spec, indent=2, sort_keys=True) + "\n"
    readme_text = render_readme(spec)

    if args.check:
        problems = []
        for path, want in ((SPEC_PATH, spec_text), (README_PATH, readme_text)):
            if not path.exists():
                problems.append(f"missing: {path.relative_to(REPO_ROOT)}")
            elif path.read_text() != want:
                problems.append(f"stale: {path.relative_to(REPO_ROOT)}")
        if problems:
            print("API docs are out of date with the app:")
            for p in problems:
                print(f"  - {p}")
            print("\nRun: python3 qc/audit/generate_api_docs.py")
            return 1
        print(f"API docs up to date ({len(spec.get('paths', {}))} paths).")
        return 0

    API_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(spec_text)
    README_PATH.write_text(readme_text)
    print(f"wrote {SPEC_PATH.relative_to(REPO_ROOT)} ({len(spec.get('paths', {}))} paths)")
    print(f"wrote {README_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
