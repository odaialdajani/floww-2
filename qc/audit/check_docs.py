#!/usr/bin/env python3
"""Docs gate — two claims a doc makes must survive a check.

1. INTERNAL LINKS RESOLVE.
   An index entry pointing at a file that is not in the tree is worse than
   no index: a reader follows it, lands nowhere, and cannot tell whether
   they are on the wrong branch or the document is abandoned.

2. NAMED PRODUCERS EXIST.
   `docs/solstice/CONTRACT_MATRIX.md` promises "every user-visible field,
   its source, adapter, store, replay and UI consumer ... implemented +
   tested unless marked otherwise". A contract matrix whose named producers
   have been renamed or deleted silently stops being a contract. Every
   identifier-shaped backticked token in that file must therefore appear
   somewhere in the source tree.

Template files are excluded: `*_template.md` and `template_*.md` contain
`{{PLACEHOLDER}}` links on purpose, and a forward-looking spoke list naming
files that do not exist yet is the template's job.

Usage:
    python3 qc/audit/check_docs.py          # exit 1 if any claim fails
    python3 qc/audit/check_docs.py --json

Tests: backend/tests/test_docs_gate.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
DOC_GLOBS = ["*.md", "docs/**/*.md", "backend/**/*.md", "frontend/**/*.md", "qc/**/*.md"]
# Explicitly claimed docs: every backticked identifier must appear in source.
CLAIM_DOCS = ["docs/solstice/CONTRACT_MATRIX.md"]
LINK_EXCLUDES = ("_template.md",)

_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_TOKEN = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)`")
_IDENT = re.compile(r"(?:[a-z_][a-z0-9_]*)|(?:[a-z][A-Za-z0-9_]*)")


def _is_template(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith("template_") or "_template" in name


# Dependency installs are not documentation: their vendored READMEs link
# relatively inside packages CI may or may not install, so scanning them
# makes the gate depend on the environment instead of the tree.
DIR_EXCLUDES = (".git", ".venv", "node_modules", "__pycache__")


def _dependency_file(path: Path) -> bool:
    return any(
        parent.name in DIR_EXCLUDES or (parent / "pyvenv.cfg").is_file()
        for parent in path.parents
        if parent != REPO_ROOT and REPO_ROOT in parent.parents
    )


def _markdown_files() -> list[Path]:
    out: list[Path] = []
    for pattern in DOC_GLOBS:
        out.extend(p for p in REPO_ROOT.glob(pattern) if p.is_file())
    return sorted({p for p in out if not _dependency_file(p)})


def find_broken_links() -> list[dict[str, str]]:
    broken: list[dict[str, str]] = []
    for doc in _markdown_files():
        if _is_template(doc):
            continue
        text = doc.read_text(encoding="utf-8", errors="ignore")
        for match in _LINK.finditer(text):
            target = match.group(1).split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if "{{" in target or "}}" in target:
                continue
            if not (doc.parent / target).resolve().exists():
                broken.append({"doc": str(doc.relative_to(REPO_ROOT)), "target": target})
    return broken


def _source_corpus() -> str:
    chunks: list[str] = []
    for base in ("backend", "frontend/src", "qc", "scripts"):
        root = REPO_ROOT / base
        if not root.is_dir():
            continue
        for directory, subdirectories, files in os.walk(root):
            subdirectories[:] = [
                name for name in subdirectories
                if name not in DIR_EXCLUDES
                and not (Path(directory) / name / "pyvenv.cfg").is_file()
            ]
            for name in files:
                path = Path(directory) / name
                if path.suffix in SOURCE_SUFFIXES:
                    try:
                        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
                    except OSError:
                        continue
    return "\n".join(chunks)


def find_unbacked_claims() -> list[dict[str, str]]:
    corpus = _source_corpus()
    findings: list[dict[str, str]] = []
    for rel in CLAIM_DOCS:
        doc = REPO_ROOT / rel
        if not doc.is_file():
            findings.append({"doc": rel, "token": "<document missing>", "reason": "DOC_MISSING"})
            continue
        text = doc.read_text(encoding="utf-8", errors="ignore")
        for raw in sorted(set(_TOKEN.findall(text))):
            # Dotted paths: check the whole thing and each segment.
            parts = [p for p in raw.split(".") if _IDENT.fullmatch(p)]
            if not parts:
                continue
            if raw != ".".join(parts):
                continue
            if not any(p in corpus for p in parts):
                findings.append({"doc": rel, "token": raw, "reason": "NO_SOURCE_REFERENCE"})
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="docs gate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    links = find_broken_links()
    claims = find_unbacked_claims()
    if args.json:
        print(json.dumps({"broken_links": links, "unbacked_claims": claims}, indent=2))
    else:
        print(f"broken internal links: {len(links)}")
        for item in links:
            print(f"  {item['doc']} -> {item['target']}")
        print(f"unbacked contract claims: {len(claims)}")
        for item in claims:
            print(f"  {item['doc']}: {item['token']} ({item['reason']})")
        if not links and not claims:
            print("OK — docs links resolve and contract claims are backed by source")
    return 1 if (links or claims) else 0


if __name__ == "__main__":
    sys.exit(main())
