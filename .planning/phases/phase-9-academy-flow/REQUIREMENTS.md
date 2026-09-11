# Phase 9 — REQUIREMENTS (Academy Flow Build)

Parent: PLAN.md (same dir). R = requirement, M = measurable acceptance.

| ID | Requirement | Wave | Acceptance (M) |
|---|---|---|---|
| R9.0 | Spikes resolve unknowns before product code | W0 | go/no-go recorded per spike (OPTION bars, [2] heat inputs, yfinance fields) |
| R9.1 | Spread bar + Fill on every Pulse row from existing quote fields | W1 | bar position == (last-bid)/(ask-bid) on 20 sampled rows; ±1% |
| R9.2 | Overview bar: NetPrem, P/C, FIR (defined), session label; RVOL honest-empty until baselines exist | W1 | values reproduce from same payload ±1%; RVOL shows "building n/20" pre-cadence |
| R9.3 | Earnings proximity col + filter; sector/industry filter | W2 | 5 sampled tickers match Finnhub calendar/profile; cached (no per-poll fetch) |
| R9.4 | ΔOI col per contract from OI history | W2 | matches next-day exchange truth on 5 sampled contracts |
| R9.5 | Strategy badge on Pulse path (spread legs flagged, not directional) | W2 | synthetic vertical/straddle fixtures badge correctly; legs never WHALE alone |
| R9.6 | Chart modal v1: Contract history + Net Premium; candle→prints bridge | W3 | opens from any Pulse row; NetPrem default view; figures match tape |
| R9.7 | Tracker v1: bookmark, live P/L, STILL-IN/PARTIAL/EXITED via OI drift | W3 | P/L within a tick of mark; staged close detected on fixture drift |
| R9.8 | Highlighting Size>OI / Vol>OI, per-tab persisted | W3 | 100% fire on synthetic fixtures incl. OI=0 edge (documented, not "fixed") |
| R9.9 | ONE per-tab substrate (tabs+cols+highlight+filters), ticker !exclude, cap/sort, CSV | W4 | prefs survive reload; 10-tab render perf unchanged; CSV round-trips |
| R9.10 | NetPrem trend + Strike distribution + Vol/OI-14d (fixture-first, live on cadence) | W4 | reproduce from snapshots on demand; placement note until B1 lands |
| R9.11 | Signed score spec + display-only + backtest harness | W5 | sign matrix unit-tested incl. put-ASK/hedge; Sharpe-gated reports |
| R9.12 | Every signal ships its evaluator; per-tag 30-min outcomes | all | evaluator file per signal; tag hit-rates visible in outcomes |
| R9.13 | Backend proposals B1–B5 tracked for lane owner; dark-pool context panel specced (FINRA ETL) | — | proposals filed with file:line; no free-data live-tape claims anywhere |

Non-requirements: paid keys, live OPRA/TRF, mobile layouts, Discord/image export,
strategy-leg modal, CBOE scraping, repo clones.
| R9.14 | Equity-type toggle + sweeps-only + side chips on Pulse | W6 | fixture: ETF-off removes all ETF rows; sweep-only keeps classified sweeps |
| R9.15 | OTM/ITM/0DTE + OPEX + strike-range + OI-growth + sentiment sliders + |score| mode | W6 | each control moves row counts monotonically on fixtures; OI-growth fixture-first |
| R9.16 | Sweep + multi-leg row icons from existing classification | W6 | synthetic sweep + vertical fixtures badge correctly |
| R9.17 | Starter tab presets ship by default (2 Academy configs) | W7 | fresh profile opens with both tabs, gates verified by mount test |
| R9.18 | In-modal investigation checklist with recorded verdicts | W7 | 6 steps checkable; verdict + reason persisted per print |
| R9.19 | Funnel empty-states with one-click widen actions | W7 | each action measurably widens (row count increases) on fixtures |
| R9.20 | Dark-pool Top-N levels overlay on heatseeker (post-B3) | W7 | lines match FINRA ETL top-N notionals ±1%; labeled with date |
| R9.21 | Right-click actions + Pulse premium/size sort with floor quirk | W7 | actions mutate filters correctly; non-Time sorts enforce $25K floor |
| R9.22 | Quiet-accumulation gate evaluated display-first (B6) | W5 | gate fires on coiled-price fixtures; never blocks alerts in v1 |
| R9.23 | Per-tag 30-min outcome hit-rates visible (B7) | W5 | tag table renders measured rates; empty-state honest below sample floor |
| R9.24 | Citation hygiene: no paper claim in copy/comments without [verified] tag; refuted attributions removed (P&P band fixed; backend docstrings → B8) | — | grep paper-names in flowseeker/ → every hit verified or labeled heuristic |
| R9.25 | V1-V3 ship (parity-dev, expiry-pin, EOD lean); V4-V6 cadence-gated with fixture proofs; V7-V8 honesty rules enforced in copy | W2/W5 | fixture tests per rule; copy audit finds zero direction claims on unsigned prints |
