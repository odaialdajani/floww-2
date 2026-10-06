# SPARK R15-5 — Outcome linkage + frozen prospective research protocol

Base `1530ccd7`. `FROZEN_PROTOCOL.md` untouched (frozen means frozen).
Zero durable admitted records → INSUFFICIENT EVIDENCE; no profitability, edge,
or session claim is made or implied.

## Linkage (existing, traced at base)

review (`scenario_decisions_v1` + `decision_reviews_v1` pending/reviewed/
waiting/skipped, 422 unknown) → decision (frozen features zone/target/stop/
horizon/policy_version + `candidate_quotes_v1`) → persisted price path
(`price_paths_v1`, now fed by default-off `solstice_price_producer.py`
`price-path-producer.v1`, 5-min swing only) → labels (`outcome_labels_v1`
keyed decision/horizon/policy/`outcome.v1` via `close_episodes/label_touch`) →
optional actual orders/fills/fees/PnL (only via gated brokerage + lifecycle,
none observed). Lineage + reason codes carried throughout.

Preserved: `NEED_EPISODE` (episodeless → pending, never labeled);
`simultaneous_unknown` (same-bar dual barrier → censored);
`OBSERVATION_GAP` (gap > max_gap_s censors; no-touch requires gap-free
coverage); `TOUCH_NO_BARRIER` indeterminate; terminal = any non-censored label
(idempotent); censored reprocessed only on longer path (`path_end_t` dedup).

Underlying barrier touches are NOT option PnL. Missing paths or unresolved
same-timestamp barriers are censored/unknown, never fabricated wins or zero
losses. Realized PnL is never derived from estimated premium, current chain,
or GEX sign.

## Prospective collection/reporting protocol (frozen when valid sessions exist)

1. Hypotheses fixed upfront: entry/confirmation/invalidation rules + data
   sufficiency thresholds recorded BEFORE analysis. No threshold selection from
   the same future outcome sample (no look-ahead).
2. Separate positive-rejection/bounce vs negative-squeeze/flush by approach,
   expiry, volume coverage, and regime. Distinct formulas/bases/units
   (raw-wall L0/L1, delta-weighted OI L2, unweighted vs volume×|delta| vs
   window ΔV) never pooled; comparable populations or disclosed exclusions.
3. Chronological holdout / walk-forward with embargo (never split within a day);
   horizons 60/180/300/900, `outcome.v1`, `abl.v1`, cost 20 bps frozen
   assumption stated per result until measured fills exist.
4. Costs: actual fees + conservatively validated rebates + spreads/slippage +
   partial fills + liquidity where trade data exists. Estimated costs are
   labeled estimates.
5. Report: net expectancy, drawdown, tail losses, exposure, uncertainty;
   independent (deduped) event counts + session-block uncertainty + regime
   coverage; SPY/QQQ first, SPX gated. Sample size, missing/censored counts,
   and benchmark labeled. Separate synthetic fixtures, paper/shadow
   observations, and real-money fills.
6. 30–60 sessions is a COLLECTION MILESTONE, not proof of edge. Zero durable
   admitted records today = insufficient empirical evidence. Real-money sizing
   requires reviewed evidence + fixed account policy; no auto-escalation, Kelly
   sizing, retraining, or parameter changes.

## Census (2 Oct 2026, base head)

Tracked DBs hold 0 solstice rows; vertical fixture self-declares synthetic;
dev-server memory snapshots are ephemeral, not admitted. Ladder smoke
(`abl.v1`) + 3-fold embargo splits execute offline (protocol runs, nothing more).
