# GEX/Gamma Correctness Audit — Findings

- **Date:** 2026-06-13
- **Status:** COMPLETE (commits staged locally, not pushed)
- **Spec:** `2026-06-13-gex-gamma-correctness-audit-design.md`
- **Method:** golden-oracle, test-first (TDD). Baseline: 116 GEX/gamma tests green → **131 green** after.

## TL;DR

The Black-Scholes math is **correct** and the existing canonical test is a **real** Hull-10e
oracle. The audit's headline suspicion (B1, a GEX scale bug) turned out to be a **correct-but-
undocumented dual convention**, where the "obvious fix" would have **corrupted frozen ML-model
features**. The right remediation was therefore proof + documentation + guardrails, not a scale
rewrite. Two genuine improvements landed (observable error-masking; doc/lint honesty). Nothing
that feeds a trained model was changed.

## Verdicts

| # | Finding | Verdict | Action taken |
|---|---|---|---|
| **B1** | `gex_aggregator` uses `S²`, `gex_history` uses `S¹` (differ by ~`spot`) | **Not a bug** — two intentional conventions: `S²` = display dollar-GEX, `S¹` = ML-feature scale (frozen model-input contract). Forcing unification would shift every trained-model feature ~100×. | Pinned **both** scales + their exact `spot` ratio with a hand-derived golden oracle; **documented** the boundary in both engine docstrings; **did not** change either scale. |
| **B2** | Risk-free rate `0.05` (bs_greeks) vs `0.045` (gex_history) | Intentional split: `0.045` is the model-locked feature rate; `0.05` is display-side. | Documented both regimes; **locked** `_RISK_FREE`/`_IV_FALLBACK` with regression tests so a future "cleanup" fails loudly. Not unified (would require retraining). |
| **B3** | Dividend yield `q=0` everywhere | Acceptable for index underlyings; was undocumented | Covered by the documented convention note. |
| **B4** | Bare `except: return 0.0` masks unexpected errors as zero-gamma | **Real defect** (silent failure) | Fixed: errors still return `0.0` (no value change) **but now log a WARNING** via `_mask_zero`, naming the failing function. TDD: 3 tests (guard stays silent, behavior preserved, masking observable). |
| **B5** | Canonical test docstring claimed `tol=1e-6`; code used `1e-3` | **Real doc defect** | Corrected the docstring to the actual per-test tolerances. |

**Confirmed-good (now pinned):** sign convention (`call +`, `put −`) consistent across both engines;
`bs_gamma` matches Hull Table 15.1 (`0.137556`); aggregator net/total/King-Node/flip-level all match
hand-derived truth.

## What changed

| File | Change | Risk |
|---|---|---|
| `backend/tests/services/test_gex_aggregator_oracle.py` | **NEW** — 12 golden-oracle tests (S² display, S¹ feature, cross-engine ratio, model-lock) | none (tests) |
| `backend/tests/test_bs_greeks_masking.py` | **NEW** — 3 tests pinning observable masking | none (tests) |
| `backend/bs_greeks.py` | `_mask_zero` helper + log on every masked exception (return value unchanged) | low — adds logging only on the rare exception path |
| `backend/services/gex_aggregator.py` | docstring: S² display-scale convention note | none (docstring) |
| `backend/services/gex_history.py` | docstring: S¹ model-locked feature-scale note | none (docstring) |
| `backend/tests/test_bs_greeks_canonical.py` | docstring tolerance honesty fix | none (docstring) |

## What was deliberately NOT changed (and why)

- **GEX scale** in either engine — the `S¹` series is a frozen model-input contract; changing it
  silently breaks inference at the trained scale and would require re-backfilling `gex_history` +
  retraining the 5 GBM models (touches frozen artifacts; out of audit scope).
- **`_RISK_FREE` (0.045) / `_IV_FALLBACK` (0.20)** in the feature path — same reason; now lock-tested.
- No forbidden files touched (`inference.py`, `dash_ui.py`, `conftest.py`, model artifacts).

## Residual recommendations (separate, model-aware work)

1. **Flat-vol feature smell:** `compute_gex_total_for_chain` uses `iv=0.20` for *every* contract
   (ignores the real IV surface). Defensible for training consistency, but a candidate to revisit
   *with* a retrain — not a silent fix.
2. **CI lint is red on pre-existing E701** (e.g. `bs_greeks.py` one-liner idiom). The repo's
   `pyproject.toml` enforces `E` but `CLAUDE.md` claims `F + E722`; reconcile the doc and/or the rules.
3. **Three sources of "GEX"** (numba aggregator, inline timeframe agg, `gflows_greeks` DuckDB).
   Consider consolidating to one engine behind the two documented scales, with the route asserting
   its output matches canonical.

## Evidence

```
$ .venv/bin/python3 -m pytest <8 GEX/gamma suites> -q
131 passed, 17 warnings           # was 116 before; +3 masking, +12 oracle, 0 regressions

$ ruff (project config) — delta on edited source files
bs_greeks.py: 29 -> 28   gex_aggregator.py: 0 -> 0   gex_history.py: 2 -> 2
new test files: All checks passed!
```
