"""G1.5: pure Discord command scaffolding (no discord.py import).

Cooldown/audit/NL-parse/fuzzy live here so a second bot can import them
instead of forking discord_bot.py. All functions are pure w.r.t. their
arguments (caller owns state); behavior matches discord_bot.py exactly.
"""
from __future__ import annotations

import collections
import difflib
import re

COOLDOWN_S: dict[str, float] = {"heatmap": 20.0, "vanna": 20.0, "walls": 5.0}

NL_READ = re.compile(r"^([A-Za-z][A-Za-z0-9.\-]{0,9})\s+(heatmap|hm|walls|w|vanna|v|gex|flip)$",
                     re.IGNORECASE)

_NL_WORD_TO_CMD = {"hm": "heatmap", "w": "walls", "v": "vanna",
                   "gex": "heatmap", "flip": "walls"}

PREFIXLESS_OPS = {"status", "clock"}


def new_cooldowns() -> dict:
    return {}


def new_audit_ring(maxlen: int = 200) -> collections.deque:
    return collections.deque(maxlen=maxlen)


def cool_check(cooldowns: dict, table: dict, user_id, cmd: str,
               now: float) -> tuple[bool, float]:
    wait = table.get(cmd, 0)
    if not wait:
        return True, 0.0
    key = (str(user_id), cmd)
    last = cooldowns.get(key, 0.0)
    if now - last < wait:
        return False, wait - (now - last)
    cooldowns[key] = now
    return True, 0.0


def audit_append(ring: collections.deque, user_id, cmd: str, t=None) -> None:
    entry = {"user": str(user_id), "cmd": cmd}
    if t is not None:
        entry["t"] = t
    ring.append(entry)


def audit_counts(ring) -> dict:
    counts: dict[str, int] = {}
    for r in ring:
        base = str(r["cmd"]).split()[0].lower()
        counts[base] = counts.get(base, 0) + 1
    return counts


def parse_nl(text: str):
    t = str(text or "").strip()
    m = NL_READ.fullmatch(t)
    if m:
        cmd = _NL_WORD_TO_CMD.get(m.group(2).lower(), m.group(2).lower())
        return cmd, m.group(1).upper()
    if t.lower() in PREFIXLESS_OPS:
        return t.lower(), None
    return None


def cooldown_line(table: dict) -> str:
    groups: dict[float, list] = {}
    for cmd, secs in table.items():
        groups.setdefault(float(secs), []).append(cmd)
    return " · ".join("/".join(sorted(g)) + f" {int(s)}s"
                      for s, g in sorted(groups.items()))


def fuzzy_hint(typed: str, known: list[str]) -> str:
    guess = difflib.get_close_matches(str(typed or ""), list(known), n=1, cutoff=0.6)
    return guess[0] if guess else ""
