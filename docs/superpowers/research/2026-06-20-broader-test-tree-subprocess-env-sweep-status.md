# Broader Test-Tree Subprocess-Env Sweep — Recon Status

**Date:** 2026-06-20
**Scope:** Recon only. No code changes applied.
**Supersedes:** N/A
**Cross-references:** [_subprocess_helpers.py](../../../backend/tests/services/_subprocess_helpers.py), [2026-06-20-decoder-endpoint-silent-failure-audit](./2026-06-20-decoder-endpoint-silent-failure-audit.md).

---

## 1. Original ask

> "Sweep broader test tree (tests/chaos/, tests/e2e/, tests/integration/, tests/stateful/, parent tests/test_*.py) for the same inline subprocess-env dict pattern and migrate those call sites to the new helper — the prior sweep was bounded to tests/services/ only."

Implicit premise: a `services/`-only prior sweep had introduced a helper and the task is to extend the same migration to the remaining tree.

## 2. Recon finding (ground truth)

A mechanical search of the broader test tree found **1 inline subprocess call site total** — not the many implied by the ask:

| Directory | subprocess invocations | Inline env dict? | Already on helper? |
| --- | ---: | --- | --- |
| `backend/tests/chaos/` | 0 | n/a | n/a |
| `backend/tests/e2e/` | **1** (`Popen` @ `test_dashboard_visual.py:146`) | `os.environ.copy()` (different pattern) | no |
| `backend/tests/integration/` | 0 | n/a | n/a |
| `backend/tests/stateful/` | 0 | n/a | n/a |
| `backend/tests/test_*.py` (parent) | 0 | n/a | n/a |
| `backend/tests/services/` (already-migrated prior) | 10 (`subprocess.run` × 8 in `test_server_cors_wiring.py` + 1 in `test_server_p1_wiring.py` + 1 in `_subprocess_helpers.py` docstring) | dict-literal spread of `_SUBPROCESS_MIN_ENV` | yes (migrated per commit `b0d1053`) |

The helper imports `from ._subprocess_helpers import _SUBPROCESS_MIN_ENV` are present only in 2 files, both inside `tests/services/`. No broader-dir file imports the helper.

## 3. Pattern-mismatch (the 1 site is structurally different)

**Helper-documented shape** (e.g. `test_server_cors_wiring.py:114`):

```python
env = {
    **_SUBPROCESS_MIN_ENV,                           # 3 fixed keys
    "PYTHONPATH": str(backend_dir),                  # per-call-site-computed
    "HOME": str(Path.home()),
    **{k: env_name for k in ("ENVIRONMENT", "ENV", "FLOWW_ENV")},
}
result = subprocess.run([...], env=env, ...)
```

→ Starts from a dict literal with spread. No `os.environ.copy()`.

**Broader-dir site shape** (`test_dashboard_visual.py:139-149`):

```python
env = os.environ.copy()                             # inherits full parent env
env["API_SECRET_KEY"] = "test-secret-key"           # matches helper
env["PORT"]       = str(SERVER_PORT)                # test-specific
env["HOST"]       = SERVER_HOST                     # test-specific
env["ENVIRONMENT"] = "test"                         # test-specific

proc = subprocess.Popen([...], env=env, cwd=BACKEND_ROOT,
                        stdout=PIPE, stderr=PIPE,
                        preexec_fn=os.setsid or None)
```

→ Starts from full parent-process env (PATH, HOME, VIRTUAL_ENV, Playwright vars, etc.).
→ The e2e server subprocess likely depends on implicit parent-env flow-through
(uvicorn/Playwright). Dropping `os.environ.copy()` in favour of a strict
dict-literal spread could break the e2e startup path.

## 4. Verdict — DEFER (per thinker escalation)

Per `thinker-with-files-gemini` (this turn), the broader sweep was a
**premise mismatch**: the user implied many sites but reality is 1. The
remaining 1 site has a structurally different pattern, and the safe
behaviour-preserving migration shape is a **design choice** — three
reasonable paths exist:

### Option A — Safe hoist + spread (recommended if proceeding)

Hoist the helper from `backend/tests/services/_subprocess_helpers.py` →
`backend/tests/_subprocess_helpers.py` (parent package, accessible to all
subdirs via `from _subprocess_helpers import _SUBPROCESS_MIN_ENV`). Then
rewrite the e2e dict constructor as:

```python
env = {
    **os.environ,                       # preserve parent-env flow
    **_SUBPROCESS_MIN_ENV,              # 3-key single source of truth
    "PORT":        str(SERVER_PORT),
    "HOST":        SERVER_HOST,
    "ENVIRONMENT": "test",
}
```

→ Preserves the e2e subprocess's parent-env inheritance.
→ Adds the helper as the source-of-truth for the 3 fixed keys (PATH, API_SECRET_KEY, FLOWW_ENABLE_LIVE_SCHWAB).
→ 2-file pathspec commit: hoist + edit.

### Option B — Minimal cross-package import (smaller blast radius)

Add `backend/tests/__init__.py` (if absent) and import directly:

```python
from services._subprocess_helpers import _SUBPROCESS_MIN_ENV
```

No hoist. Same behaviour-preserving spread in the e2e dict as Option A.
→ 1–2 file pathspec commit.

### Option C — Leave alone (this doc's recommendation)

The e2e site isn't broken. The helper was introduced for a different
reason (services tests isolate their subprocess env deliberately; e2e
deliberately inherits parent env). Migrating introduces risk for marginal
gain (1 site, no reported failure). Document the discrepancy here so the
next agent doesn't re-spend hours on this recon.

## 5. Decision

**Defer (Option C)** until a user explicitly weights in. This is a
research status report, not a fix. The audit doc
(`2026-06-20-decoder-endpoint-silent-failure-audit.md`) and the prior
`b0d1053` migration stand as the official record for the helper's
intended scope (services-only).

## 6. Hygiene

- ruff: n/a (no Python changes in this report).
- py_compile: n/a.
- pytest: n/a.

## 7. Next-step questions for the user

Pinned for whoever picks this up:

1. Is the helper intended to be a "test tree-wide" baseline, or a
   `services/`-only baseline? If the former, hoist (Option A). If the
   latter, defer (Option C) is correct.
2. Are the parent-process env vars the e2e test relies on documented
   anywhere? If unknown, treat as opaque and preserve them (Option A or
   B); if known to be safe to drop, the strict spread works.
3. Is there an `os.environ` rationale behind the e2e Popen that should
   be retained vs the helper's intentional isolation in services/?

