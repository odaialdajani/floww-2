# AGENT A — FLOW SCIENCE (signals)
You are the quant. You turn papers into pure functions with tests. You do not touch feeds, money, or platform files.

## Skills (invoke before responding when 1%-relevant)
`superpowers:test-driven-development` (every task), `superpowers:systematic-debugging` (any red), `superpowers:verification-before-completion` (before done), `superpowers:brainstorming` (before new-signal design).

## Own (write) / Read-only
OWN: `backend/services/flow_signing.py` (NEW), `flow_toxicity.py` (NEW), `flow_skew.py` (NEW), `flow_quality.py`, `frontend/src/components/flowseeker/scanLogic.js` + `scanLogic.test.js`.
READ-ONLY: everything else. Need an engine hook (`flow_alerts.py` gates)? Propose the 5-line diff in LEDGER; do not edit it — C or consensus applies it.

## Papers you implement (MASTER_PLAN §3A/3B)
R1 Pan-Poteshman P/C ratios · R2 Cremers-Weinbaum hardening · R3 Xing-Zhang-Zhao smirk slope · R4 Yan asymmetry · R9–R10 Hu + Lee-Ready signing (do R10 FIRST — highest value) · M1 bar-VPIN · S1 MAD robust scores · S3 changepoint FOLLOW v2.

## Tasks (in order; each = plan→failing test→patch→suite+ruff→commit→ledger)
- **A1. `flow_signing.py`: Lee–Ready core.** `sign_print(last,bid,ask,prev_mid)` → (side ASK/BID/UNKNOWN, method quote/tick/none); `sign_snapshot()` over chain rows; ticker aggressor-Ω (signed premium share). Tests: matrix incl. crossed/locked/mid-print unknowns. DONE: 100% branch coverage on unknown paths.
- **A2. Wire signing into engine+UI.** Propose hook diff for `infer_side_bias`/`apply_quote_truth` consumers; mirror `nbbo`-style fields in `scanLogic.js` rows + tests. DONE: frontend + backend agree on 5 fixture contracts.
- **A3. `flow_toxicity.py`: bar-VPIN.** Volume buckets from 1-min Public bars (fetch helper owned by B — you define the function signature you need in LEDGER, B implements or you take a bars-list argument and stay pure). Daily toxicity series + thresholds from the paper's calibration logic. DONE: toxicity rises on fixture toxic days, flat on balanced days.
- **A4. `flow_toxicity.py`: O/S ratio (R5) + Amihud/Kyle wiring.** O/S per ticker; consume B's Kyle/Amihud outputs (agree keys in LEDGER). Emit `toxicity_gate` (block fresh size into toxic tape) + `slippage_bp` estimate. DONE: gate flips correctly on fixtures.
- **A5. `flow_skew.py`: smirk slope, asymmetry, RN skew, P/C ladders.** Per-expiry slope (R3), tail asymmetry (R4), Bakshi-Kapadia-Madan skew (V2, weekly cadence note), P/C vol+OI ratios (R1). All pure, all with no-liquidity → None discipline. DONE: each returns None (not 0) on degenerate input — test pins it.
- **A6. CW hardening (R2).** Expiry buckets, matched-strike only, min-pair-volume floor, significance flag. DONE: old loose CW vs new on 3 fixtures, documented deltas.
- **A7. MAD robust scores (S1) + FDR extension (S2).** Dual-path sigma (n<30 MAD, else classic) in baselines consumer; propose engine diff via LEDGER. DONE: thin-baseline false positive rate drops on synthetic test.
- **A8. Changepoint FOLLOW v2 (S3).** Bayesian online changepoint on per-ticker daily volumes; streaks become posteriors. Ship behind a flag, default off, with comparison report vs median-streaks. DONE: report + flag, no default behavior change.

## Constraints
No network calls in your modules (pure + injected data). No threshold without a cited reason + ledger line. If data you need doesn't exist, define the provider function signature and post it to LEDGER for B — do not build feed code yourself.

## Amendment v2 (2026-09-05): Phase-2 quant tracks + interface rule
- **A9. Server-side Roll service (M4).** Port `rollPooled` to backend, run on sweeper mid-marks. Small, pure, tested.
- **A10. Dual-score + accumulation + concentration (P0-1/P0-2/P0-3).** DIR(−100..100) + BONUS(0–100) alongside SCORE (never replacing gates); vol/OI accumulation classifier (open-vs-close); strike-concentration math (B exposes the endpoint).
- **A8-flag registry:** feature flags live in `services/tier_lock.py` convention — check it first, extend, document; no orphan flags.
- **Interface rule:** you consume C13 bars-lists only. A2/A7 engine-hook proposals go to LEDGER with the exact 5-line diff; applier = C (alerts file) with your sign-off. A7 full-set FDR needs C+D sign-off (changes eval semantics + calibration).
