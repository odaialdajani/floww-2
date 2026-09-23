# Solstice COMMISSION — account-level verification (23 Sep 2026)

Redacted: no secrets, no account IDs. Read-only probes only (9 requests,
sequential, ~0.1–0.4s each — no quota stress). No orders placed; execution
remains disarmed by design.

## Account
- Auth/token mint works; 2 accounts; trading account selected explicitly
  (options LEVEL_2). No silent first-account fallback.

## Commissioned (this account)
- SPY equity quote live with bid/ask/last source timestamps.
- SPY expirations: 32 series including 0DTE listing for 2026-09-23.
- SPY chain shape confirms documented fields (bid/ask/last + per-side
  timestamps, cumulative volume, OI, nested Greeks); parsed timestamps
  preserved with provenance; OI stays null when absent (never 0-filled).
- Targeted Greeks endpoint works (250-contract ceiling respected; probed 3).
- Bars: 252 daily SPY bars; instrument metadata exposes option price
  increments (tick rules available, no hardcoded ticks).

## Gated / unavailable (this account)
- SPX/SPXW chain: HTTP 400 on all three request shapes tried
  (INDEX-option-underlying SPX, INDEX-option-underlying SPXW, EQUITY SPX).
  SPX INDEX *quote* works, but index-option *chains* are not retrievable —
  SPX interpretation stays behind index-specific commissioning.
- OI effective dating: measured 2026-09-23 over 2,296 SPY contracts across 6
  expiries — `oi_effective_date` is None on ALL contracts, OI missing on none
  (756 observed-zero). OI cadence is therefore unobservable from any vendor
  field: OI is last-known with unknown effective date. Cross-day OI-change
  ranking stays gated (the enrichment already skips undated comparisons);
  reason code `OI_EFFECTIVE_UNKNOWN` registered.
- Greek timestamps: vendor Greeks (100% of sampled contracts, all with bid
  timestamps) carry NO Greek-specific timestamp. Quote age is the reported
  proxy, kept separate from Greek-time certainty (`GREEK_TIME_UNKNOWN`).
- OI publication cadence: single-session observation only; needs multi-day
  capture before asserting update times.
- 429/Retry-After behavior: not observed (limits not probed by hammering).
- Expired-option history retention: unprobed (record live sessions regardless).
- Bracket/child lifecycle: disarmed and unprobed against production.

## Live-session capture (in-process, read-only builds)
- SPY: Public source, 684 contracts, 116 strikes, 2 walls (snapshot recorded).
- QQQ: Public source, 724 contracts, 126 strikes, 4 walls (snapshot recorded).
- Replay round-trip verified (strikes/walls/contracts resolve by snapshot ID).
- Cross-snapshot compare correctly reports `history_unavailable` (one
  snapshot per ticker — never a one-point trend).
- Recorder is in-memory DuckDB in this process; file-backed persistence is
  a deployment concern, not a code gap.

## Data rights
Individual Trader API, personal-use program. Captured observations stay local;
redistribution or multi-user deployment needs the applicable partnership
before it happens.
