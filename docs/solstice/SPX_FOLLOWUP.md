# SPX index-chain follow-up — draft for vendor/account support (23 Sep 2026)

Account: LEVEL_2 options (IDs redacted). Read-only market-data probes only.

## Observed (2026-09-23, sequential, minimal quota)
- `INDEX` quote for SPX: **works** (spot-level quote returned).
- Option expirations **HTTP 400** for all three shapes:
  1. symbol SPX + `UNDERLYING_SECURITY_FOR_INDEX_OPTION`
  2. symbol SPXW + `UNDERLYING_SECURITY_FOR_INDEX_OPTION`
  3. symbol SPX + `EQUITY`
- Equity/ETF path unaffected: SPY chain (341 contracts over 2 expiries in
  commissioning; 2,296 over 6 expiries in OI dating), 32 SPY expiries, Greeks,
  bars, and instrument metadata all return normally.

## Questions
1. Which symbol + instrument-type combination returns SPX/SPXW option
   expirations and chains for an Individual Trader API account at LEVEL_2?
2. Are index options behind a separate entitlement or approval on this account?
3. If entitled, is there a distinct root/series convention (SPX vs SPXW vs
   weekly vs standard) required by the request?
4. Does the 400 reflect permissions, an unknown symbol, or a wrong request
   type — and what exact error code accompanies it?

## Our handling until resolved
SPX interpretation stays gated behind index-specific commissioning (resolver
exists; chain unavailable). SPY/QQQ commissioned. No repeated probing.
