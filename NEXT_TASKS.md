# NEXT_TASKS.md

> Current handoff (2026-09-11): [REMAINING_WORK.md](REMAINING_WORK.md) records the
> full unfinished AI/UI work, blockers, verification gaps and publication scope.
> The older tasks below are retained; their historical status and blockers have
> not been revalidated or marked complete by the current integration work.

## Phase 5 Causal Inference — Complete (2026-05-23)

### Shipped ✅
- Granger causality test suite (re-run): QI→Vol significant (p=0.016), VPIN→Returns not sig.
- Retail CPR/OI Skew backtest script (scripts/backtest_retail_strategy.py)
- Both directional and long-only contrarian variants tested
- Finding: contrarian signal has edge (+0.41% expectancy/trade) but needs regime filter
- Reports: causal_granger_20260523.md, backtest_retail_20260523.md
- Committed: 54e281d

### Key Findings
- Quote Imbalance Granger-causes volatility (lags 4-7, all p<0.05)
- VPIN CDF does NOT Granger-cause returns or volatility at daily frequency
- CPR+OI Skew contrarian: 60% WR, 1.73 PF, but -12.32% total return in 2024 bull market
- Short side is the problem — shorting a bull market kills the strategy
- Long-only variant has positive per-trade expectancy, needs more data

### Next Steps
- Add regime filter to backtest (trend-following overlay to avoid counter-trend trades)
- Re-run Granger on intraday data when available (tick-level VPIN likely stronger)
- Test on 2022 bear market data (contrarian should shine there)
- Wire ensemble into Dash UI toxicity gauge
- Production training on real MongoDB gex_history data (needs WiFi)

### Blocked on MongoDB (need WiFi)
- Real VPIN training data from gex_history collection
- Walk-forward backtest on historical data
- FOMC day validation
