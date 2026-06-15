# GEX/Gamma Correctness Audit — Design Spec

- **Date:** 2026-06-13
- **Status:** Draft — awaiting Nav review
- **Scope owner:** architect (Claude) — execution held to TDD + verification gates
- **Method (approved):** Golden-oracle, test-first. Fix as found.

---

## 1. Goal

Establish an independent **golden-oracle** correctness harness for the GEX/gamma path and
reconcile every divergence it exposes, end-to-end:

```
bs_greeks.bs_gamma ─┐
gex_history._bs_gamma ─┼─► aggregation ─► API ─► frontend (BarHeatmap / TrinityView)
gflows_greeks (DuckDB) ─┘
```

Success = the numbers the product shows are provably correct against hand-derived ground
truth, and the tests fail if that math ever drifts (no fixture/mocking masking).

## 2. Context — the path as it actually exists

There are **three** independent gamma/GEX surfaces, discovered by reading the code (not the notes):

| Engine | File | Gamma source | GEX scale | r |
|---|---|---|---|---|
| Numba aggregator | `backend/services/gex_aggregator.py` | consumes pre-computed γ | `γ·OI·100·S²·0.01` | n/a |
| Timeframe agg | `backend/services/gex_history.py::calc_gex_timeframes` | inline `_bs_gamma` | `γ·OI·100·S·0.01` | `0.045` |
| Greeks API | `backend/routes/greeks.py` | reads `gflows_greeks` DuckDB table | (upstream gflows) | (upstream) |
| Shared BS lib | `backend/bs_greeks.py::bs_gamma` | canonical formula | n/a | `0.05` |

The `bs_gamma` formula itself is **correct** (hand-verified against Hull Table 15.1:
gamma = `φ(d1)/(S·σ·√T)` = 0.137556). The `test_bs_greeks_canonical.py` oracle is **real**
(Hull 10e values), not fabricated. The risk lives one layer up, at the aggregation seam.

## 3. Verified findings (the backlog)

Each will be **proven by a failing test** in P1 before any fix (per project test discipline).

- **B1 — GEX scale inconsistency (headline).** `gex_aggregator` uses `S²`, `gex_history` uses `S¹`
  (`gex_aggregator.py:93` vs `gex_history.py:292`). For S≈100 the two engines disagree by ~100×.
  Shape-preserving, so invisible on a chart but wrong for any absolute threshold.
- **B2 — Risk-free rate hardcoded & inconsistent.** `RISK_FREE_RATE=0.05` (`bs_greeks.py:9`) vs
  `_RISK_FREE=0.045` (`gex_history.py:42`). No dynamic treasury rate reaches this path — the
  notes' claim is false here.
- **B3 — Dividend yield ignored.** Both engines effectively use `q=0` (bs_greeks defaults `q=0`;
  gex_history omits the `e^{-qT}` term). Acceptable for indices, but undocumented and divergent
  from a "with-dividends" reading.
- **B4 — Silent masking.** `except Exception: return 0.0` in every Greek (`bs_greeks.py`,
  `gex_history.py:267`) and NaN→0.0 in `greeks.py:89-96`. A numerical failure is indistinguishable
  from a genuine zero, biasing aggregate GEX toward 0 with no signal.
- **B5 — Test gaps.** No golden oracle for the *aggregator* (sign/scale/net/King-Node/flip).
  Gamma exact-tested at one moneyness point only. Docstring claims `tol=1e-6`; code uses `1e-3`.

**Confirmed-good (pin, don't change):** sign convention is consistent (`call=+1, put=−1`) across
both compute engines; the BS formulas; the existing Hull oracle.

## 4. The oracle

Independent ground truth, computed by hand and asserted with tight tolerance:

1. **Greek layer** — extend `test_bs_greeks_canonical.py`:
   - exact gamma at ≥3 (moneyness × maturity) points, hand-derived;
   - tighten gamma/vega tolerance to the documented `1e-6` (or fix the docstring to the achievable
     bound — whichever the values support);
   - put-gamma == call-gamma identity (same strike) pinned explicitly.
2. **Aggregator layer (NEW)** — `backend/tests/services/test_gex_aggregator_oracle.py`:
   - a small fixed chain (≥2 strikes × ≥2 expiries, calls+puts) with **hand-derived**
     `net_gex`, `gex_1d` per strike, `total_gex` / `total_negative_gex`, King Node strike, and one
     interpolated flip level;
   - asserts the **canonical** scale (decision D1) so the wrong-scaled engine fails until fixed;
   - pins the sign convention (flip a put OI → net_gex moves the documented direction).
3. **Cross-engine agreement (NEW)** — one test feeding identical inputs to both compute engines and
   asserting they agree (to the canonical definition). This is the test that B1/B2 currently break.

Oracle values are derived in the test files (P1), not here, to avoid an unverified number in the spec.

## 5. Work plan (TDD, smallest patch per fix)

- **P0 — Baseline.** `pwd` check; `git fetch && git status`; run the 8 GEX/gamma test files +
  `ruff check` via `backend/.venv/bin/python3`; capture the green baseline count.
- **P1 — Build oracle (failing first).** Author the tests in §4. Confirm each fails for the
  expected reason (B1 scale, B2 rate, B5 tolerance) — a failing test that fails for the *wrong*
  reason is not evidence.
- **P2 — Reconcile / fix.**
  - B1: converge both engines on the canonical scale (D1). Single shared helper if clean.
  - B2: single shared risk-free source (D2).
  - B4: make masking observable (D3) — count/propagate instead of silent 0.0; add a test that a
    forced error is *visible*.
  - B3/B5: document `q=0`; fix tolerance docstring/values.
- **P3 — Plumbing trace.** Confirm whether any caller passes a real `r`/`iv` or everything defaults.
  Add a test that fails if `r` silently defaults when a caller intends otherwise.
- **P4 — Verify.** Full GEX/gamma module sweep green + ruff clean; write a findings summary
  (`docs/` note); leave commits staged for Nav to push (no remote writes by me).

## 6. Decisions for Nav (material — please confirm at review)

- **D1 — Canonical GEX scale: `S²` (standard dealer GEX) vs `S¹`.** *Recommend `S²`*
  (SqueezeMetrics-standard dollar gamma per 1% move). This **changes displayed magnitudes** in any
  surface currently using the `S¹` engine → borderline-architectural, so explicit sign-off wanted.
- **D2 — Risk-free rate: unify to one value/source.** *Recommend* a single shared
  `RISK_FREE_RATE` constant now (0.045 vs 0.05 must collapse to one); wiring a live treasury rate is
  out of scope unless you want it folded in.
- **D3 — Silent-zero policy.** *Approved:* keep guard-clause zeros for invalid/expired inputs;
  replace the bare `except: return 0.0` with observable behavior (count dropped contracts / propagate)
  + tests.

## 7. Non-goals (YAGNI)

- No configurable dealer-positioning model (keep the customer-long sign assumption; pin + document it).
- No live treasury-rate integration (unless D2 says otherwise).
- No frontend redesign — only verify the API→display contract carries correct, consistently-scaled numbers.
- No touching the third (`gflows_greeks`) pipeline's internals this pass — only assert its output's
  scale/sign matches canonical, and report if it doesn't.

## 8. Guardrails & risks

- **Forbidden files** (per `CLAUDE.md`): if any fix traces into `inference.py`, `dash_ui.py`,
  `conftest.py`, or model artifacts → **STOP and report**, do not edit.
- **Test discipline:** every fix gets a test that fails before and passes after; never skip/xfail a
  passing test; if a passing test breaks, the change is wrong → revert + root-cause.
- **No remote writes:** commits are authored locally with HEREDOC + inline evidence and left for Nav
  to push.
- **Risk:** D1 changes numbers users see. Mitigated by pinning both old/new with tests and a clear
  before/after in the findings summary so the change is auditable, not silent.

## 9. Done criteria

1. Golden oracle exists for Greek + aggregator layers and **fails** on injected drift.
2. B1, B2, B4 reconciled; B3/B5 documented/fixed; cross-engine agreement test green.
3. Full GEX/gamma sweep + ruff green on `backend/.venv`.
4. Findings summary written; commits staged with evidence for Nav to push.
