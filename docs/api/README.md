# API Reference

<!-- GENERATED FILE - DO NOT EDIT BY HAND. -->
<!-- Regenerate: python3 qc/audit/generate_api_docs.py -->
<!-- Verify:     python3 qc/audit/generate_api_docs.py --check -->

Total endpoints: 390
Route groups: 104

Generated from the live FastAPI app, so every path below is a real,
callable route rather than a hand-copied guess.

## (root) (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/` | Root Head |
| HEAD | `/` | Root Head |
| GET | `/api/` | Api Root |

## admin (6 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/admin/rate-limits` | Get Rate Limits |
| GET | `/api/admin/trading/circuit-breaker/log` | Circuit Breaker Log |
| POST | `/api/admin/trading/circuit-breaker/reset` | Circuit Breaker Reset |
| POST | `/api/admin/trading/circuit-breaker/trip` | Circuit Breaker Trip |
| GET | `/api/admin/trading/status` | Trading Status |
| POST | `/api/admin/trading/transition` | Trading Transition |

## advanced (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/advanced/{ticker}` | Advanced Analytics |

## agent (16 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/agent/ask` | Ask |
| GET | `/api/agent/budget` | Budget |
| POST | `/api/agent/cancel/{turn_id}` | Cancel |
| GET | `/api/agent/claims` | Claims |
| GET | `/api/agent/handoffs` | Native Handoff History |
| POST | `/api/agent/handoffs` | Save Native Handoff |
| GET | `/api/agent/history` | History |
| GET | `/api/agent/models` | Models |
| GET | `/api/agent/prefs` | Prefs |
| PUT | `/api/agent/prefs` | Save Prefs |
| POST | `/api/agent/session` | Session |
| POST | `/api/agent/session/logout` | Logout Session |
| POST | `/api/agent/session/recover` | Recover Session |
| POST | `/api/agent/session/rotate` | Rotate Session |
| GET | `/api/agent/stream/{turn_id}` | Stream |
| GET | `/api/agent/turn/{turn_id}` | Get Turn |

## agent-hub (8 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/agent-hub/archetypes` | List Archetypes |
| POST | `/api/agent-hub/archetypes` | Create Archetype |
| DELETE | `/api/agent-hub/archetypes/{name}` | Delete Archetype |
| GET | `/api/agent-hub/archetypes/{name}` | Get Archetype |
| PUT | `/api/agent-hub/archetypes/{name}` | Update Archetype |
| POST | `/api/agent-hub/archetypes/{name}/disable` | Disable Archetype |
| POST | `/api/agent-hub/archetypes/{name}/enable` | Enable Archetype |
| GET | `/api/agent-hub/status` | Hub Status |

## ai (5 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/ai/analyze-regime` | Analyze Regime |
| POST | `/api/ai/analyze-trade` | Analyze Trade |
| POST | `/api/ai/explain-signal` | Explain Signal |
| GET | `/api/ai/status` | Get Ai Status |
| POST | `/api/ai/summarize-day` | Summarize Day |

## alert-quality (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/alert-quality` | Alert Quality |

## alerts (10 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/alerts` | List Alerts |
| POST | `/api/alerts` | Create Alert |
| GET | `/api/alerts/check/{ticker}` | Check Alerts |
| POST | `/api/alerts/snapshot` | Add Snapshot |
| GET | `/api/alerts/status` | Get Alert Status |
| GET | `/api/alerts/summary` | Get Alerts Summary |
| GET | `/api/alerts/types` | List Alert Types |
| GET | `/api/alerts/whales` | Get Whale Tracks |
| DELETE | `/api/alerts/{alert_id}` | Delete Alert |
| GET | `/api/alerts/{ticker}` | Get Alerts |

## alpaca (12 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/alpaca/account` | Get Account |
| GET | `/api/alpaca/bars/{ticker}` | Get Bars |
| GET | `/api/alpaca/clock` | Get Clock |
| POST | `/api/alpaca/order` | Place Order |
| POST | `/api/alpaca/order/option` | Place Option Order |
| GET | `/api/alpaca/orders` | Get Orders |
| GET | `/api/alpaca/position-journal-drift/{symbol}` | Position Journal Drift |
| DELETE | `/api/alpaca/position/{symbol}` | Close Position |
| GET | `/api/alpaca/positions` | Get Positions |
| POST | `/api/alpaca/reconcile-close` | Reconcile Close |
| GET | `/api/alpaca/reconciliation-exceptions` | Get Reconciliation Exceptions |
| GET | `/api/alpaca/status` | Get Status |

## alpha (12 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/alpha/crypto/{symbol}` | Get Crypto Price |
| GET | `/api/alpha/earnings/{ticker}` | Get Earnings |
| GET | `/api/alpha/forex/{from_currency}/{to_currency}` | Get Forex Rate |
| GET | `/api/alpha/historical/{ticker}` | Get Historical |
| GET | `/api/alpha/intraday/{ticker}` | Get Intraday |
| GET | `/api/alpha/market-status` | Get Market Status |
| GET | `/api/alpha/news` | Get News |
| GET | `/api/alpha/options/{ticker}` | Get Options Chain |
| GET | `/api/alpha/overview/{ticker}` | Get Company Overview |
| GET | `/api/alpha/quote/{ticker}` | Get Quote |
| GET | `/api/alpha/technical/{ticker}/{indicator}` | Get Technical Indicator |
| GET | `/api/alpha/top-gainers-losers` | Get Top Gainers Losers |

## alpha-flow (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/alpha-flow` | Alpha Flow |
| GET | `/api/alpha-flow/dates` | Alpha Flow Dates |

## anomaly (7 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/anomaly/ensemble` | Get Ensemble Prediction |
| GET | `/api/anomaly/ensemble/state` | Get Ensemble State |
| POST | `/api/anomaly/ensemble/update` | Update Ensemble |
| GET | `/api/anomaly/{ticker}` | Get Anomaly State |
| POST | `/api/anomaly/{ticker}/load` | Load Trained Model |
| GET | `/api/anomaly/{ticker}/status` | Get Detector Status |
| POST | `/api/anomaly/{ticker}/update` | Update Anomaly |

## auth (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/auth/dev-token` | Dev Token |

## backtest (5 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/backtest/is-oos` | Run Is Oos |
| POST | `/api/backtest/monte-carlo` | Run Monte Carlo |
| GET | `/api/backtest/report/{ticker}` | Get Backtest Report |
| POST | `/api/backtest/run` | Run Backtest |
| POST | `/api/backtest/walk-forward` | Run Walk Forward |

## briefing (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/briefing/{ticker}` | Get Briefing |
| GET | `/api/briefing/{ticker}/html` | Get Briefing Html |
| GET | `/api/briefing/{ticker}/send` | Briefing Send |

## chain (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/chain` | Get Chain |
| GET | `/api/chain/{ticker}` | Chain |

## chain_consensus (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/chain_consensus/{ticker}` | Chain Consensus Route |

## charm-integral (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/charm-integral/{ticker}` | Charm Integral Endpoint |

## compare (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/compare` | Compare |

## consensus_drift (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/consensus_drift/{ticker}` | Consensus Drift Endpoint |

## contract (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/contract/{ticker}` | Contract |
| GET | `/api/contract/{ticker}/{strike}/{expiry}` | Contract Strike |

## correlation (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/correlation` | Correlation |

## daily-checklist (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/daily-checklist/{ticker}` | Daily Checklist |

## data (6 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/data/full/{ticker}` | Get Full Data |
| GET | `/api/data/health` | Get Data Health |
| GET | `/api/data/news/{ticker}` | Get News |
| GET | `/api/data/quote/{ticker}` | Get Quote |
| GET | `/api/data/status` | Get Data Status |
| GET | `/api/data/{ticker}` | Get Ticker Data |

## data-quality (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/data-quality/history` | Data Quality History |
| GET | `/api/data-quality/{ticker}` | Data Quality |

## databento (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/databento/breaker/status` | Databento Breaker Status |
| GET | `/api/databento/usage` | Databento Usage |

## deep-dive (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/deep-dive/{ticker}` | Deep Dive |

## discord (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/discord/status` | Discord Status |
| POST | `/api/discord/test` | Discord Test |

## dual_gex (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/dual_gex/{ticker}` | Dual Gex |

## earnings (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/earnings` | Earnings |
| GET | `/api/earnings/ticker/{ticker}/detail` | Earnings Ticker Detail |
| GET | `/api/earnings/week` | Earnings Week |

## ensemble (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/ensemble/state` | Get Ensemble State |
| POST | `/api/ensemble/update` | Update Ensemble |

## errors (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/errors/clear` | Errors Clear |
| GET | `/api/errors/summary` | Errors Summary |

## exposure_profile (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/exposure_profile/{ticker}` | Exposure Profile Endpoint |

## flashalpha (12 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/flashalpha/dashboard/{symbol}` | Get Dashboard |
| GET | `/api/flashalpha/earnings-vrp/{symbol}` | Get Earnings Vrp |
| GET | `/api/flashalpha/exposure/{symbol}` | Get Exposure |
| GET | `/api/flashalpha/flow-blocks/{symbol}` | Get Flow Blocks |
| GET | `/api/flashalpha/flow-live/{symbol}` | Get Flow Live |
| GET | `/api/flashalpha/flow/{symbol}` | Get Flow |
| GET | `/api/flashalpha/gex/{symbol}` | Get Gex |
| GET | `/api/flashalpha/max-pain/{symbol}` | Get Max Pain |
| GET | `/api/flashalpha/narrative/{symbol}` | Get Narrative |
| GET | `/api/flashalpha/status` | Get Status |
| GET | `/api/flashalpha/volatility/{symbol}` | Get Volatility |
| GET | `/api/flashalpha/zero-dte/{symbol}` | Get Zero Dte |

## flow (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/flow/{ticker}` | Flow Sse |

## flow-alerts (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/flow-alerts` | Flow Alerts |

## flow-digest (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/flow-digest` | Flow Digest |

## flowseeker (29 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/flowseeker/alerts/feed` | Institutional Alert Feed |
| GET | `/api/flowseeker/alerts/quality` | Institutional Alert Quality |
| GET | `/api/flowseeker/alerts/stream` | Institutional Alert Stream |
| GET | `/api/flowseeker/alerts/{symbol}` | Unusual Activity Alerts |
| POST | `/api/flowseeker/auto-trade/execute` | Auto Trade Execute |
| GET | `/api/flowseeker/auto-trade/preview` | Auto Trade Preview |
| POST | `/api/flowseeker/auto-trade/risk-reset` | Auto Trade Risk Reset |
| GET | `/api/flowseeker/chain/{symbol}` | Options Chain |
| GET | `/api/flowseeker/drilldown/{symbol}` | Drilldown |
| POST | `/api/flowseeker/journal/close` | Journal Close |
| GET | `/api/flowseeker/journal/stats` | Journal Stats |
| GET | `/api/flowseeker/journal/trades` | Journal Trades |
| GET | `/api/flowseeker/live` | Live Flow |
| GET | `/api/flowseeker/market-session` | Market Session |
| GET | `/api/flowseeker/model` | Calibration Model |
| GET | `/api/flowseeker/outcomes` | Alert Outcomes |
| POST | `/api/flowseeker/outcomes/refresh` | Alert Outcomes Refresh |
| GET | `/api/flowseeker/public/chain/{ticker}` | Public Chain Flat |
| GET | `/api/flowseeker/regime/{ticker}` | Regime |
| GET | `/api/flowseeker/risk/killswitch` | Risk Killswitch Status |
| POST | `/api/flowseeker/risk/killswitch/reset` | Risk Killswitch Reset |
| POST | `/api/flowseeker/risk/killswitch/trip` | Risk Killswitch Trip |
| GET | `/api/flowseeker/scan` | Market Scan |
| GET | `/api/flowseeker/scan-public` | Public Market Scan |
| GET | `/api/flowseeker/scan/history` | Scan History |
| POST | `/api/flowseeker/scan/refresh` | Force Refresh Scan |
| GET | `/api/flowseeker/screen` | Screen Options |
| GET | `/api/flowseeker/universe/leaderboard` | Universe Leaderboard |
| GET | `/api/flowseeker/universe/scan` | Universe Scan |

## gamma-flip (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/gamma-flip/{ticker}` | Gamma Flip |

## gex (5 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/gex/spx` | Gex Spx |
| GET | `/gex/flippoints/{ticker}` | Get Flip Points |
| GET | `/gex/flow-analysis/{ticker}` | Get Flow Analysis |
| GET | `/gex/liquidity/{ticker}` | Get Gex Liquidity Analysis |
| GET | `/gex/term-structure/{ticker}` | Get Gex Term Structure |

## gex-timeframes (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/gex-timeframes/{ticker}` | Gex Timeframes |

## greeks (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/greeks/profile/{ticker}` | Get Greeks Profile |

## hawkes (4 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/hawkes/{ticker}/fit` | Fit Hawkes |
| GET | `/api/hawkes/{ticker}/intensity` | Get Intensity |
| POST | `/api/hawkes/{ticker}/simulate` | Simulate Hawkes |
| GET | `/api/hawkes/{ticker}/state` | Get Hawkes State |

## health (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/health` | Health Check |
| GET | `/health` | Health Alias |

## heatmap (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/heatmap/{ticker}` | Heatmap |

## heatseeker (18 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/heatseeker/air-pockets` | Air Pockets Route |
| GET | `/api/heatseeker/beach-ball` | Beach Ball Route |
| GET | `/api/heatseeker/flip-zones` | Flip Zones Route |
| GET | `/api/heatseeker/history/{ticker}` | Get History |
| GET | `/api/heatseeker/latest/{ticker}` | Get Latest |
| GET | `/api/heatseeker/node-classification` | Node Classification Route |
| GET | `/api/heatseeker/node-confluence` | Node Confluence Route |
| GET | `/api/heatseeker/node-lifecycle` | Node Lifecycle Route |
| GET | `/api/heatseeker/price-history/{ticker}` | Price History |
| GET | `/api/heatseeker/rainbow-road` | Rainbow Road Route |
| GET | `/api/heatseeker/reverse-rug` | Reverse Rug Route |
| GET | `/api/heatseeker/rolling-floors-ceilings` | Rolling Floors Ceilings Route |
| POST | `/api/heatseeker/snapshot/{ticker}` | Trigger Snapshot |
| GET | `/api/heatseeker/stacked-nodes` | Stacked Nodes Route |
| GET | `/api/heatseeker/top-movers/{ticker}` | Get Top Movers |
| GET | `/api/heatseeker/trinity-confluence` | Trinity Confluence Route |
| GET | `/api/heatseeker/tug-of-war` | Tug Of War Route |
| GET | `/api/heatseeker/velocity-mode` | Velocity Mode Route |

## hedge-impulse (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/hedge-impulse/{ticker}` | Hedge Impulse |

## history (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/history/{ticker}` | History |

## implied-pdf (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/implied-pdf/{ticker}` | Implied Pdf |

## insider (6 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/insider/latest` | Insider Latest Endpoint |
| POST | `/api/insider/latest/accumulate` | Insider Latest Accumulate Endpoint |
| GET | `/api/insider/top` | Insider Top Endpoint |
| POST | `/api/insider/top/accumulate` | Insider Top Accumulate Endpoint |
| GET | `/api/insider/{ticker}` | Insider Ticker Endpoint |
| POST | `/api/insider/{ticker}/accumulate` | Insider Ticker Accumulate Endpoint |

## iv_mid (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/iv_mid/{ticker}` | Iv Mid |

## liquidity (4 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/liquidity/{ticker}` | Get Liquidity Metrics |
| POST | `/api/liquidity/{ticker}/amihud` | Update Amihud |
| GET | `/api/liquidity/{ticker}/fragility` | Get Fragility |
| POST | `/api/liquidity/{ticker}/kyle` | Update Kyle |

## live (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/live/policy` | Live Policy |
| POST | `/api/live/policy` | Live Policy Update |
| POST | `/api/live/tape/stop` | Live Tape Stop |

## llm (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/llm/analyze-trade` | Llm Analyze Trade |
| POST | `/api/llm/generate` | Llm Generate |
| GET | `/api/llm/providers` | Llm Providers |

## market (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/market/catalog` | Catalog Page |
| GET | `/api/market/provider-updates` | Provider Updates |

## max_pain (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/max_pain/{ticker}` | Max Pain Route |

## max_pain_drift (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/max_pain_drift/{ticker}` | Max Pain Drift Endpoint |
| GET | `/api/max_pain_drift/{ticker}/per_expiry_history` | Max Pain Drift Per Expiry History Endpoint |

## memory (4 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/memory/gex` | Memory Gex |
| GET | `/api/memory/recall/{ticker}` | Memory Recall |
| GET | `/api/memory/summary/{ticker}` | Memory Summary |
| POST | `/api/memory/trade` | Memory Trade |

## metrics (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/metrics` | Prometheus Metrics |

## microstructure (9 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/microstructure/anomaly/{ticker}` | Anomaly Endpoint |
| GET | `/api/microstructure/gex-surface/{ticker}` | Gex Surface Endpoint |
| GET | `/api/microstructure/hawkes/{ticker}` | Hawkes Endpoint |
| GET | `/api/microstructure/liquidity/{ticker}` | Liquidity Endpoint |
| GET | `/api/microstructure/nodes/{ticker}` | Nodes Endpoint |
| GET | `/api/microstructure/toxicity-dashboard` | Toxicity Dashboard |
| GET | `/api/microstructure/trinity` | Trinity Endpoint |
| GET | `/api/microstructure/vol-surface/{ticker}` | Vol Surface Endpoint |
| GET | `/api/microstructure/vpin/{ticker}` | Vpin Endpoint |

## ml (32 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/ml/attach-outcomes` | Attach Outcomes |
| POST | `/api/ml/batch-predict` | Batch Predict |
| GET | `/api/ml/briefing/{ticker}` | Ml Briefing |
| GET | `/api/ml/calibration` | Get Calibration Default |
| GET | `/api/ml/calibration/{ticker}` | Get Calibration |
| GET | `/api/ml/compare` | Ml Compare |
| GET | `/api/ml/dashboard` | Ml Dashboard |
| GET | `/api/ml/dashboard/{ticker}` | Ml Dashboard |
| GET | `/api/ml/drift/{ticker}` | Drift Report |
| GET | `/api/ml/ensemble` | Ensemble Prediction |
| GET | `/api/ml/ensemble/{ticker}` | Get Ensemble |
| GET | `/api/ml/features/{ticker}` | Get Features |
| GET | `/api/ml/health` | Ml Health All |
| GET | `/api/ml/health/{ticker}` | Ml Health Check |
| GET | `/api/ml/model-info/{ticker}` | Model Info |
| GET | `/api/ml/models` | List Models |
| GET | `/api/ml/models/{ticker}` | Get Model Info |
| GET | `/api/ml/outcome/accuracy` | Get Accuracy |
| POST | `/api/ml/outcome/batch-record` | Batch Record |
| POST | `/api/ml/outcome/compute` | Compute Outcomes |
| GET | `/api/ml/outcome/recent` | Get Recent |
| POST | `/api/ml/outcome/record` | Record Prediction |
| GET | `/api/ml/predict/{ticker}` | Predict Direction |
| POST | `/api/ml/predict/{ticker}` | Predict |
| POST | `/api/ml/promote/{model_id}` | Promote Model |
| GET | `/api/ml/regime/{ticker}` | Get Regime |
| POST | `/api/ml/register` | Register Model |
| POST | `/api/ml/reload/{ticker}` | Ml Reload Model |
| GET | `/api/ml/retrain-status/{ticker}` | Retrain Status |
| POST | `/api/ml/retrain/{ticker}` | Trigger Retrain |
| GET | `/api/ml/rolling-accuracy/{ticker}` | Rolling Accuracy |
| POST | `/api/ml/train` | Trigger Training |

## movers (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/movers` | Movers |

## news (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/news/article` | News Article Endpoint |
| GET | `/api/news/{ticker}` | News Ticker Endpoint |
| GET | `/api/news/{ticker}/history` | News History Endpoint |

## nexus (5 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/nexus/comments` | Get Comments |
| POST | `/api/nexus/comments` | Post Comment |
| GET | `/api/nexus/leaderboard` | Get Leaderboard |
| GET | `/api/nexus/status` | Nexus Status |
| POST | `/api/nexus/waitlist` | Join Waitlist |

## occ_volume (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/occ_volume/{ticker}` | Occ Volume Endpoint |

## opportunity (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/opportunity/{ticker}` | Opportunity Endpoint |

## paper-trading (7 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/paper-trading/attribution` | Pnl Attribution |
| POST | `/api/paper-trading/estimate-cost` | Estimate Execution Cost |
| POST | `/api/paper-trading/execute` | Execute Paper Order |
| GET | `/api/paper-trading/history` | Trade History |
| GET | `/api/paper-trading/portfolio` | Portfolio Summary |
| GET | `/api/paper-trading/status` | Paper Trading Status |
| POST | `/api/paper-trading/submit` | Submit Paper Order |

## patterns (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/patterns/glossary` | Patterns Glossary |

## performance (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/performance/stats` | Performance Stats |

## portfolio (5 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/portfolio/{name}` | Get Portfolio |
| POST | `/api/portfolio/{name}/hedge` | Hedge |
| POST | `/api/portfolio/{name}/position` | Add Position |
| DELETE | `/api/portfolio/{name}/position/{index}` | Remove Position |
| GET | `/api/portfolio/{name}/scenario` | Scenario |

## position-size (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/position-size` | Position Size |

## position-sizing (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/position-sizing` | Position Sizing |

## predictive (4 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/predictive/alerts` | Get Predictive Alerts |
| GET | `/api/predictive/chaos` | List Chaos Scenarios |
| POST | `/api/predictive/chaos/run` | Run Chaos Scenario |
| GET | `/api/predictive/forecasts` | Get Forecasts |

## preferences (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/preferences/` | Get Preferences |
| POST | `/api/preferences/` | Set Preferences |
| POST | `/api/preferences/theme` | Set Theme |

## pressure-cloud (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/pressure-cloud/{ticker}` | Pressure Cloud |

## provider-health (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/provider-health` | Provider Health |

## public (12 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/public/account` | Get Account |
| GET | `/api/public/bars/{ticker}` | Get Public Bars |
| GET | `/api/public/chain/{ticker}` | Get Public Chain |
| GET | `/api/public/expirations/{ticker}` | Get Public Expirations |
| GET | `/api/public/history/{ticker}` | Get Public History |
| POST | `/api/public/order` | Place Order |
| POST | `/api/public/order/{order_id}/cancel` | Cancel Order |
| GET | `/api/public/orders` | Get Orders |
| GET | `/api/public/portfolio` | Get Portfolio |
| GET | `/api/public/portfolio/raw` | Get Public Portfolio |
| GET | `/api/public/quotes/{ticker}` | Get Public Quotes |
| GET | `/api/public/technical/{ticker}/{indicator}` | Get Public Technical |

## quant (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/quant/full` | Quant Full |
| GET | `/api/quant/signals` | Quant Signal Catalog |

## regime (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/regime/{ticker}` | Regime |

## regime-stats (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/regime-stats/{ticker}` | Regime Stats |

## regime_persistence (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/regime_persistence/{ticker}` | Regime Persistence Endpoint |

## replay (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/replay/start` | Start Replay |
| GET | `/api/replay/status` | Replay Status |
| POST | `/api/replay/stop` | Stop Replay |

## retail-flow (5 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/retail-flow/{ticker}` | Get Retail Flow Snapshot |
| POST | `/api/retail-flow/{ticker}/compute` | Compute Retail Flow |
| GET | `/api/retail-flow/{ticker}/cpr` | Get Cpr |
| GET | `/api/retail-flow/{ticker}/oi-change` | Get Oi Change |
| GET | `/api/retail-flow/{ticker}/score` | Get Flow Score |

## rnd (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/rnd/{ticker}` | Risk Neutral Density Endpoint |
| GET | `/api/rnd/{ticker}/{expiry}` | Risk Neutral Density Path Endpoint |

## screener (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/screener/income` | Screener Income |

## sentiment (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/sentiment` | Sentiment Route |

## social (4 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/social/flow/{ticker}` | Get Flow |
| GET | `/api/social/report/{ticker}` | Get Full Report |
| GET | `/api/social/sentiment/{ticker}` | Get Sentiment |
| GET | `/api/social/status` | Get Pipeline Status |

## solstice (23 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/solstice/attribute/{ticker}` | Attribute |
| GET | `/api/solstice/capability` | Capability |
| GET | `/api/solstice/evidence/{ticker}` | Evidence |
| GET | `/api/solstice/manifest/{ticker}` | Manifest |
| POST | `/api/solstice/outcomes/close` | Outcomes Close |
| GET | `/api/solstice/patterns/{ticker}` | Patterns |
| GET | `/api/solstice/price-paths/comparable` | Price Path Comparable |
| GET | `/api/solstice/price-paths/expiries` | Price Path Expiries |
| GET | `/api/solstice/price-paths/points` | Price Path Points |
| GET | `/api/solstice/price-paths/sessions` | Price Path Sessions |
| GET | `/api/solstice/price-paths/status` | Price Paths Status |
| GET | `/api/solstice/recorder_health` | Recorder Health |
| GET | `/api/solstice/regime/{ticker}` | Regime |
| GET | `/api/solstice/replay/{snapshot_id}` | Replay |
| POST | `/api/solstice/scan` | Scan |
| GET | `/api/solstice/scan/leaderboard` | Leaderboard |
| GET | `/api/solstice/scout/{ticker}` | Scout |
| GET | `/api/solstice/snapshot/{ticker}` | Snapshot |
| GET | `/api/solstice/vanna/{ticker}` | Vanna |
| GET | `/api/solstice/walls/{ticker}` | Walls |
| GET | `/api/solstice/{ticker}/contract` | Contract Detail |
| GET | `/api/solstice/{ticker}/decisions` | Decisions List |
| POST | `/api/solstice/{ticker}/decisions/{decision_id}/review` | Save Review |

## spot (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/spot/{ticker}` | Spot |

## strategy (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/strategy/evaluate` | Strategy Evaluate Endpoint |

## strike_cone (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/strike_cone/{ticker}` | Strike Cone Endpoint |

## surface (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/surface/{ticker}` | Surface |

## tick-cache (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/tick-cache/{ticker}` | Tick Cache |

## tickers (2 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/tickers` | List Tickers |
| GET | `/api/tickers/all` | List All Tickers |

## trinity (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/trinity` | Trinity |
| GET | `/api/trinity/align` | Get Trinity Alignment |
| GET | `/api/trinity/{ticker}` | Get Trinity For Ticker |

## turboquant (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| POST | `/api/turboquant/generate` | Turboquant Generate |
| GET | `/api/turboquant/presets` | Turboquant Presets |
| GET | `/api/turboquant/status` | Turboquant Status |

## uoa (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/uoa/{ticker}` | Uoa |

## vanna (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/vanna/{ticker}` | Vanna Endpoint |

## vanna-exposure (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/vanna-exposure/{ticker}` | Vanna Exposure Endpoint |

## version (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/version` | Version |

## vol (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/vol/realized/{ticker}` | Realized Volatility Endpoint |

## vol-surface (3 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/vol-surface/{ticker}` | Get Vol Surface |
| POST | `/api/vol-surface/{ticker}/sabr` | Fit Sabr |
| POST | `/api/vol-surface/{ticker}/svi` | Fit Svi |

## vpin (4 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/vpin/{ticker}` | Get Vpin State |
| GET | `/api/vpin/{ticker}/history` | Get Vpin History |
| POST | `/api/vpin/{ticker}/ingest` | Ingest Trade |
| GET | `/api/vpin/{ticker}/toxicity` | Get Toxicity |

## wheel_income (1 endpoints)

| Method | Path | Summary |
|--------|------|---------|
| GET | `/api/wheel_income/{ticker}` | Wheel Income Alias |
