# INSTITUTIONAL LOOP HANDOFF — DRAFT (Agent D, evolving to final gate)

> Status: DRAFT. Final numbers + sync outcomes land at H23–24.
> Branch: `phase9/agent2-flowseeker`. Mid-loop health (H3): **4832 passed,
> 64 skipped, 1 xfailed, 0 failed** (344s) + flowseeker jest 262/262.

## What changed (by agent, with commits)

**A — flow science.** `services/flow_signing.py` (NEW, A1): per-contract
Lee–Ready (quote rule on last-vs-mid, tick fallback last-vs-prev_mid,
degenerate→UNKNOWN). Pending: A2/A7 engine-hook diffs, frontend hygiene
labels (C5), kyle/spread/velocity attach (C4 activation).

**B — data plane.** `services/market_bars.py` (NEW, B1): C13
`get_1min_bars`/`get_daily_bars`/`get_adv_21d`, budget acquire on `_get`,
OHLC quarantine, stale-serve, `last_error`. Pending: B4 `acquire_n` +
adaptive slice (chain fetch debits **0** vs 2+N cost — D quantified),
`age_s` on stale-serve (C8), `note_sweep()` hook (C11 sweep age),
`math.isfinite` guard in `_validate` (passes `inf` today).

**C — money loop (claims C1–C8 complete).** `flow_alert_moves` horizon-leg
table + readers (C1, D-signed-off); staged calibration attach (C2) +
`get_calibration_status()` accessor (D-consumed); Kelly sizing (C3);
execution advisor TAKE/WORK/SKIP (C4, patient-default until A/B attach
inputs); earnings protocol (C5); campaign promotion verified pre-existing
(C6); rule value table (C7, wired to /outcomes/refresh); bridge
determinism + timestamp audit (C8, engine-level idempotency/fee/kill-switch
OPEN); whale tracker end-to-end incl. badge endpoint (P1-7).

**D — proof.** Sweep recorder/replayer + digest + keyed diff + golden
fixture (`sweep_replay.py`); boundary validators + `Quarantine` +
`quarantine_total` (D3); feed fault matrix (D4); C11 health section +
`sweep_watch` + dead-man gauge (D5); secret scanner + gate test (D5/D7);
feed-economics + bars audits (D6). Doctrine review: DarkPoolPanel
compliant (honest empty-state copy, no claimed data).

## What was measured

- Backend full suite 4832/0-fail mid-loop (+87 vs 4745 pre-loop baseline).
- Frontend flowseeker 18 suites / 262 tests via canonical `craco test`
  (bare `npx jest` fails 7 suites on CSS transform — runner discipline).
- Replay: byte-identical alerts on frozen snapshots; drift fails loudly.
- Single-flight: 3 concurrent pollers → 1 expiries flight. Cache hits: 0
  tokens + 0 upstream. Fuzz: 500 seeded malformed bars, never raise.
- Ruff clean on all D paths, every D commit.

## What is still proxy (labeled, not hidden)

- Premiums: BS estimates until `premium_truth` overlay; `p_move`
  uncalibrated until stage ≥ 1 (min-n gates).
- Sweep/burst reads are chain-implied proxies with confidence labels —
  no claimed verified sweeps/HIRO/dark-pool data (P2-10 upheld).
- Whale P&L is an underlying-leg proxy. C4 slippage default 25bps
  one-way; thresholds provisional to Sync-3 kill/keep.

## What Nav must decide

1. **Rotate the Databento key** in tracked root `test_dbn_live.py`
   (Law-8; gate scanner now fails loud on it — file untouched by D).
2. B-open vs defer: `acquire_n`, `age_s`, `note_sweep`, `inf` guard.
3. A-open vs defer: C5 frontend labels, C4 input attach.
4. Frozen-file needs: none raised by D to date.
5. Sync gates H6/H12/H18 + final calibration report v1 (D chairs).
