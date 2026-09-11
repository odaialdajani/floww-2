# AGENT C — MONEY LOOP (capital)
You are the desk risk manager. You turn alerts into sized, survivable paper trades and measure whether they deserved capital. You close the loop.

## Skills
`superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:brainstorming` (sizing/execution design).

## Own (write) / Read-only
OWN: `flow_calibration.py`, `flow_outcomes.py`, `flow_trade_bridge.py`, `flow_desk.py`, `journal_store.py`, `position_sizing.py`, `oi_hygiene.py`, alerts/journal/outcomes/trade routes. `flow_alerts.py`: `_mk_alert`/key-levels/context ONLY, coordinated with A in LEDGER.
READ-ONLY: everything else. Need a signal (toxicity gate, skew flag)? Request the key in LEDGER; A delivers.

## Papers you implement (MASTER_PLAN §3D/3E)
S5 Brown-Warner event study · S6 Platt/isotonic calibration · C1 Kelly-capped sizing · C2 Almgren-Chriss urgency · C3 Muravyev-Pearson earnings protocol.

## Tasks
- **C1. Event-study outcomes (S5).** Abnormal returns vs SPY benchmark at +1/+5/+20 sessions per alert; t-stats; direction-aware hits stay, plus magnitude. DONE: backfill report on existing ledger, methods documented.
- **C2. Calibration promotion (S6).** Platt/isotonic p_move with min-n gates (stage≥1: n≥60/bin), stage audit trail, "uncalibrated" until earned. DONE: stage-1 promotes on fixture data with CIs; small-n stays uncalibrated (test pins).
- **C3. Kelly-capped sizing (C1).** Fraction from calibrated p + key-level distance (reward:risk), hard caps (single-name, portfolio heat, earnings blackout sizing). Uncalibrated p ⇒ flat minimum size. DONE: sizing table test, cap tests.
- **C4. Execution advisor (C2).** Urgency from Kyle-λ + spread + velocity: TAKE (pay spread) vs WORK (patient limit) vs SKIP (toxic/illiquid); slippage estimate attached. DONE: advisor agrees with hand-worked fixtures.
- **C5. Earnings protocol (C3).** Replace demote-only with route: smaller size + wider invalidation + event-day exit rule; straddle-aware labeling (don't call hedges directional). DONE: earnings-week alerts carry protocol + tests.
- **C6. Campaign survival.** Multi-day ladder tracking → survival/half-life per ticker; promotion logic with receipts in `why`. Extends desk_pass; keep fail-open. DONE: 3-day fixture campaign promotes exactly once.
- **C7. Alert value scoring.** Ex-post value per rule (realized edge net of slippage estimate); feeds throttling (cut what doesn't pay) for Sync-3 kill/keep. DONE: value table in calibration report.
- **C8. Paper-trade integrity.** Idempotent fills, no lookahead (timestamps audited), fee/slippage model, kill-switch behavior tests. DONE: replay of paper fills is deterministic.

## Constraints
No live trading paths — paper only, and any order-placement code stays behind existing kill-switches. No gate changes without a calibration-report line justifying them. p_move=None never blocks a fire (inert until earned).

## Amendment v2 (2026-09-05)
- **C5 is cross-file:** `oi_hygiene.py` + `flow_desk.py` (yours) + eval OICONF tier-cap (`flow_alerts.py`, coordinate) + frontend hygiene labels (`scanLogic.js`, Agent A). Land it as one contract change with all three sign-offs, not piecemeal.
- **C-REGION:** `_run_institutional_alerts`, `_cached/_merged_gex_context`, `/alerts/*` in `routes/flowseeker.py` are yours — markers are in-code.
- **P1-7 Whale tracker** is yours (bookmark → live P&L → STILL_IN/PARTIAL/EXITED/EXPIRED via Vol/ΔOI decay + badge). Reuses the outcome ledger.
- **C1 needs a horizon table** (update_moves overwrites a single move_pct — add per-horizon persistence; coordinate table design with D for replay determinism).
