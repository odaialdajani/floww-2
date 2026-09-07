"""Evidence ledger + cite-don't-type (plan v3 L2).

Deterministic ids: ev + short_hash(tool, params, source, as_of) so the
golden grader compares ids across runs. The model writes {{evXXXX}} and
derived forms; the server substitutes formatted values. A bare numeral
in a factual slot is a protocol violation, not a fuzzy match.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

REF_RE = re.compile(r"\{\{(ev[0-9a-f]{8}|div:[^}|]+|delta:[^}|]+|dist:[^}|]+)\}\}")
BARE_NUM_RE = re.compile(r"(?<![\w{}$%])\d+(?:\.\d+)?(?![\w}%])")


def short_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:8]


def ev_id(tool: str, params: dict[str, Any], source: str, as_of: str | None) -> str:
    try:
        canon = json.dumps(params or {}, sort_keys=True, default=str)
    except Exception:
        canon = str(params)
    return "ev" + short_hash(tool, canon, source or "", as_of or "")


def format_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        av = abs(value)
        if av >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if av >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        return f"{value:,}"
    if isinstance(value, float):
        av = abs(value)
        if av >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if av >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        if av >= 10_000:
            return f"{value:,.0f}"
        if av >= 100:
            return f"{value:,.1f}"
        return f"{value:.2f}"
    return str(value)


def substitute(text: str, ledger: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    """Replace {{refs}} with formatted values. Returns (rendered, flagged)."""
    flagged: list[str] = []

    def _one(m: re.Match) -> str:
        ref = m.group(1)
        try:
            if ref.startswith("ev"):
                entry = ledger.get(ref)
                if entry is None:
                    flagged.append(f"unknown:{ref}")
                    return "[missing evidence]"
                if entry.get("status") == "failed":
                    flagged.append(f"failed:{ref}")
                    return "[unavailable]"
                return format_value(entry.get("value"))
            if ref.startswith(("div:", "delta:", "dist:")):
                kind, rest = ref.split(":", 1)
                ids = rest.split("|")[0].split(",")
                ids = [i.strip() for i in ids if i.strip()]
                vals = []
                for i in ids:
                    e = ledger.get(i)
                    if e is None or e.get("status") == "failed":
                        flagged.append(f"bad-ref:{i}")
                        return "[unavailable]"
                    try:
                        vals.append(float(e.get("value")))
                    except Exception:
                        flagged.append(f"non-numeric:{i}")
                        return "[unavailable]"
                if kind == "div" and len(vals) == 2 and vals[1] != 0:
                    return f"{vals[0] / vals[1] * 100:.1f}%"
                if kind == "delta" and len(vals) == 2:
                    base = vals[1]
                    if base == 0:
                        return "n/a"
                    return f"{(vals[0] - base) / abs(base) * 100:+.1f}%"
                if kind == "dist" and len(vals) == 2 and vals[1] != 0:
                    return f"{(vals[0] - vals[1]) / abs(vals[1]) * 100:+.2f}%"
                flagged.append(f"bad-form:{ref}")
                return "[unavailable]"
        except Exception:
            flagged.append(f"error:{ref}")
            return "[unavailable]"
        flagged.append(f"bad-form:{ref}")
        return "[unavailable]"

    return REF_RE.sub(_one, text), flagged


def lint_no_markdown(text: str) -> str:
    """Strip markdown the prompt forbids (* # -); server re-orders sections."""
    out = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith(("#",)):
            s = s.lstrip("#").strip()
        out.append(s)
    return "\n".join(out)


def find_bare_numerals(text: str) -> list[str]:
    """Residual numeric lint on text with refs already substituted out."""
    stripped = REF_RE.sub("", text)
    return BARE_NUM_RE.findall(stripped)
