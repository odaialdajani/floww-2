"""
D-gate secret scanner (Agent D, D5/D7). Flags pasted secrets in code,
logs, and notebooks. `.env` files are the sanctioned home for keys and
are skipped; everything else with a live-looking secret fails the gate.
Run at every sync gate and the final gate.
"""
from __future__ import annotations

import os
import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("databento_key", re.compile(r"\bdb-[A-Za-z0-9]{12,}")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{10,}")),
    ("github_token", re.compile(r"\bghp_[A-Za-z0-9]{20,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----")),
    ("assigned_secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]([A-Za-z0-9_\-]{12,})['\"]"
    )),
]

_ALLOW_MARKERS = ("test", "example", "placeholder", "redacted", "...", "your_", "changeme")

_ENUM_VALUE = re.compile(r"^[A-Z][A-Z_]*$")

_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".hypothesis",
              ".pytest_cache", "dist", "build", ".next", "data"}
_SKIP_SUFFIXES = (".pyc", ".pyo", ".png", ".jpg", ".ico", ".joblib", ".pt")
_SKIP_FILES = {".env"}


def _allowed(value: str) -> bool:
    v = value.lower()
    return any(m in v for m in _ALLOW_MARKERS)


def scan_text(text: str) -> list[tuple[str, str]]:
    """Return [(pattern_name, snippet)] hits in one blob of text."""
    hits: list[tuple[str, str]] = []
    for name, rx in _PATTERNS:
        for m in rx.finditer(text or ""):
            if _allowed(m.group(0)):
                continue
            if name == "assigned_secret" and _ENUM_VALUE.match(m.group(2)):
                continue  # screaming-enum constant, not a credential
            hits.append((name, m.group(0)[:60]))
    return hits


def scan_tree(root: str) -> list[dict[str, str]]:
    """Walk a repo tree; return [{path, line, pattern}] findings."""
    findings: list[dict[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn in _SKIP_FILES or fn.startswith(".env."):
                continue
            if fn.endswith(_SKIP_SUFFIXES):
                continue
            if ".env." in fn:
                continue
            p = os.path.join(dirpath, fn)
            try:
                with open(p, errors="replace") as f:
                    content = f.read(2_000_000)
            except (OSError, UnicodeError):
                continue
            for i, line in enumerate(content.splitlines(), 1):
                for name, _snippet in scan_text(line):
                    findings.append({"path": p, "line": str(i), "pattern": name})
                    break
    return findings
