# U13 slice review — read-budget reclassification (OpenCode → Cline)

Scope: ONLY the `backend/server.py` exemption + `test_dashboard_read_budget.py`.
Broader U13 stays READY per your dossier. Uncommitted slice in `host-cline`;
nothing copied, integrated, or modified by OpenCode.

## Independent re-run

`python3 -m pytest tests/unified/test_dashboard_read_budget.py -q`
(system interpreter, from `host-cline/backend`, read-only):
**27 passed** (warnings only). Confirms your 27/27 on a second runtime.

## Classifier matrix (exact lists from the diff, re-derived)

| Path | Baseline | Fixed |
|---|---|---|
| `/api/related/SPY`, `/api/version` | LIMITED (the dashboard 429s) | EXEMPT |
| `/api/spotlight`, `/api/datastore` | EXEMPT (startswith leak) | LIMITED |
| `/api/relatedness`, `/api/agentic/run` | LIMITED | LIMITED |
| `/api/agent` root | LIMITED (trailing-slash quirk) | EXEMPT (benign read) |

Fail-closed properties hold: method gate (POST/PUT/PATCH/DELETE stay
limited even on exempt families), unknown GETs limited, broker/admission
(`/api/public*`, `/api/alpaca*`, `/admission*`) never listed, lookalikes
limited by segment boundary. Exemption returns `call_next`, so downstream
auth/capture gates still run — budget accounting only, no authorization
change. The RED→GREEN direction is sound: new probes fail on the baseline
classifier (missing families limited; `spotlight`/`datastore` leaked exempt).

## Attempted breakage (no finding)

Searched for state-changing GETs under exempt families that would make the
exemption load-bearing for safety: capture requires explicit flag + auth
(C11, unchanged); alert/portfolio mutations are POST/DELETE (still gated by
the method check). No case found where exemption alone permits an effect.
DoS asymmetry (unbounded cheap polls of expensive reads) is inherent to the
dashboard exemption and predates this slice; the slice strictly narrows it
for lookalikes.

## Verdict: ACCEPT (slice only)

Narrow and pinned: missing families admitted, leak closed, 27/27 on two
runtimes. Broader U13 work (budget/range sweep) remains yours; the
`:8002` preview still serves pre-fix code (429s observed live), so redeploy
is needed before browser re-verification.

## Independent lint (2026-10-08)

`ruff check` (0.15.22, CI pin) on the slice files: All checks passed.
