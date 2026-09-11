# OWNERSHIP — path → agent map for the institutional loop
Single source of truth, machine-read by `scripts/loop_guard.sh` (do not
reformat the table: `| bash-glob | OWNER | note |`, first match wins,
top-down). Unanimous agreement + LEDGER line to amend. Version: v1.

SHARED = cross-region file: commits touching it need the other owner's
sign-off line in LEDGER (script enforces via LOOP_SIGNOFF). LEDGER.md
itself is append-only (all agents append rows; D owns structure).

| Path glob | Owner | Note |
|---|---|---|
| backend/services/flow_signing.py | A | A1 Lee-Ready core |
| backend/services/flow_toxicity.py | A | A3/A4 toxicity + O/S |
| backend/services/flow_skew.py | A | A5 skew/slope/RN-skew |
| backend/services/flow_quality.py | A | A6 CW, factors |
| backend/services/roll_spread.py | A | A9 server-side Roll |
| frontend/src/components/flowseeker/scanLogic.js | A | rule mirrors |
| frontend/src/components/flowseeker/scanLogic.test.js | A | rule mirrors |
| backend/tests/services/test_flow_signing.py | A | A1 tests |
| backend/tests/services/test_flow_toxicity.py | A | A3/A4 tests |
| backend/tests/services/test_flow_skew.py | A | A5 tests |
| backend/services/market_bars.py | B | B1 C13 bars/ADV |
| backend/services/public_api.py | B | broker client |
| backend/services/public_api_adapter.py | B | chain/bars adapter |
| backend/services/public_scanner.py | B | universe sweeper |
| backend/services/public_budget.py | B | token bucket |
| backend/services/cache_router.py | B | chain cache |
| backend/services/fetch_coordinator.py | B | fetch routing |
| backend/services/kyle_lambda.py | B | M2 bars rewrite |
| backend/services/amihud_illiquidity.py | B | M3 bars wiring |
| backend/services/vpin_engine.py | B | bars adapter only |
| backend/services/vpin_toxicity.py | B | VPIN family |
| backend/routes/public_api.py | B | public routes |
| frontend/src/components/flowseeker/FlowseekerProBlademap.jsx | B | scanner UI |
| backend/tests/services/test_market_bars.py | B | B1 tests |
| backend/tests/services/test_roll_spread.py | A | A9 tests |
| backend/tests/services/test_public_*.py | B | public path tests |
| backend/services/flow_calibration.py | C | C2 calibration |
| backend/services/flow_outcomes.py | C | C1/C7 outcomes |
| backend/services/flow_trade_bridge.py | C | C3/C4 sizing+execution |
| backend/services/flow_desk.py | C | desk pass, campaigns |
| backend/services/journal_store.py | C | journal lifecycle |
| backend/services/position_sizing.py | C | Kelly caps |
| backend/services/oi_hygiene.py | C | earnings protocol |
| backend/routes/alerts*.py | C | alert routes |
| backend/routes/journal*.py | C | journal routes |
| backend/routes/outcomes*.py | C | outcome routes |
| backend/routes/trade*.py | C | trade routes |
| backend/tests/services/test_flow_outcomes.py | C | outcome tests |
| backend/tests/services/test_flow_trade_bridge.py | C | bridge tests |
| backend/tests/services/test_flow_desk.py | C | desk tests |
| backend/tests/services/test_flow_calibration*.py | C | calibration tests |
| backend/tests/chaos/* | D | chaos matrix |
| backend/tests/perf/* | D | latency/budget tests |
| backend/tests/routes/test_health*.py | D | health tests |
| backend/services/chain_replay.py | D | replay harness |
| backend/tests/**/test_*replay*.py | D | replay tests |
| backend/tests/**/test_*chaos*.py | D | chaos tests |
| backend/services/observability.py | D | observability |
| backend/services/meta_observability.py | D | provider health |
| backend/routes/health*.py | D | health routes |
| docs/handoff/* | D | handoff notes |
| institutional_loop/LEDGER.md | D | structure (rows append-only by all) |
| institutional_loop/OWNERSHIP.md | D | this map (unanimous to amend) |
| backend/services/flow_alerts.py | SHARED | A scoring + C levels; region split by function |
| backend/tests/services/test_flow_alerts.py | SHARED | engine contract tests |
| backend/tests/services/test_flow_quality.py | SHARED | gate pins (DEFAULT_EVAL_OPTS) |
| backend/routes/flowseeker.py | SHARED | B-REGION scan/chain + C-REGION alerts |
| backend/server.py | SHARED | B sweep region + D health/startup |
| institutional_loop/CONTRACTS.md | SHARED | unanimous to amend |
| institutional_loop/MASTER_PLAN.md | SHARED | unanimous to amend |
| * | UNOWNED | allowed but printed as warning for D's sync review |
| backend/services/heatmap_image.py | B | Solstice PNG renderer |
| backend/services/discord_ops.py | B | Discord webhook/commands/approve |
| backend/discord_bot.py | B | Solstice gateway process |
| backend/routes/discord.py | B | /api/discord status+test |
| backend/routes/alpaca.py | B | Alpaca paper routes + journal hook |
| backend/tests/services/test_heatmap_image.py | B | renderer tests |
| backend/tests/services/test_discord_ops.py | B | discord ops tests |
| backend/alpaca_client.py | B | Alpaca paper client (options/bracket/reads) |
| backend/tests/services/test_alpaca_paper.py | B | paper venue pins |
| frontend/src/App.js | SHARED | surgical trade-submit + panel mounts only (Nav-approved scope) |
