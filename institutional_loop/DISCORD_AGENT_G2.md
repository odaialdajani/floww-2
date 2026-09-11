# G2 — ALERT QUALITY (what reaches Discord). You own every pixel posted.
Read `institutional_loop/DISCORD_MASTER_PLAN.md` (§3 pipeline), `CONTRACTS.md`
(C6 alert dict), then post ready + first 2 claims to LEDGER and start.

OWN: `services/discord_ops.py` (format/gate/digest/validator only), its tests.
READ-ONLY elsewhere (need engine/route changes? propose the diff in LEDGER).
Skills: TDD, systematic-debugging, verification-before-completion.

## Tasks
- **G2.1 Validator hardening.** Fuzz `validate_alert_for_post` (None/NaN/
  empty-string/zero/missing-key matrices); every render field covered.
  Zero stays measurable, everything else unknown stays home.
- **G2.2 429 + retry.** Mock 429 sequences with Retry-After; implement
  backoff + per-sweep POST budget; prove with chaos test (U4).
- **G2.3 Missed-post replay (U5).** Persist post attempts (alert key, ts,
  status) to a tiny DuckDB table; `!missed` (bot surface — hand the command
  spec to G1) replays failures. Design doc first, 10 lines max in LEDGER.
- **G2.4 Tier/rule tuning from the ledger.** Pull per-rule precision from
  flow_outcomes; propose DISCORD_MIN_TIER/RULES values with numbers, don't
  guess. Uncalibrated rules stay reachable but clearly labeled.
- **G2.5 Digest readability.** Field order, number formatting, and the
  overflow line — screenshot-review with Nav (post samples to the test
  channel, iterate twice max, then lock).

Constraints: never weaken the validator to make traffic flow (red means the
producer is fixed forward). No trading logic. No new market-data reads —
formatting only.
