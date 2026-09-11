# Honest Copy Checklist — Agent 4 (per surface)

Every new/changed surface must pass each applicable line. CI-grep terms in parentheses.

- Pulse row: SIDE labeled inferred ("ASK (inferred)") · sweep labeled proxy · NO_QUOTE state on
  missing bid/ask · RVOL "needs baseline" when baseline missing · ΔOI dash + "snapshot-based" tooltip.
- ROUND-2: HOW-TO-READ/tooltips banned: "where the print crossed", "lifted the offer", "aggressive buy"
  (without "inferred"), "(last print", "latest print". Required: "inferred", "no tape", "proxy".
- ROUND-2: sweep definitions must be single-sourced (scanLogic owner); "Sweep (urgent)" and
  "High-Conviction" language on proxy classifications flagged until reconciled.
- ROUND-7: venue nouns banned without venue data — "multi-exchange", "cross-venue", "multi-venue fill".
  "(heuristic)"/"(proxy)" does NOT license a venue noun. Approved: "multi-print burst proxy".
- ROUND-2: quote-missing rows must render SIDE unknown ("—"), never voi-fallback ASK/BID.
- Scanner: classification column carries proxy footnote · "true sweep" never appears (`true sweep`,
  `confirmed sweep`, `sweep detected` banned).
- Overview bar: FIR formula shown · session label formula-gated · RVOL honest-empty.
- Alerts: no "guaranteed" · no "will move" · suppression counters visible, never silent drops.
- Tracker: close detection labeled proxy · P/L mark priority (mid→last→stale) disclosed.
- Chart modal: history labeled snapshot-based where applicable · timezone + stale stamps.
- Dark pool surfaces: no side/direction/buy/sell/bullish/bearish (`dark pool buying|selling`,
  `bullish dark`, `bearish dark`, `institutions are long here` banned) · fixed unsigned-prints footer ·
  paid-gate note for real-time TRF.
- FINRA/Reg SHO panels: delay stamps · "venue mix, no direction" · shorts as positioning context.
- Retail/sentiment: BJZZ scope footnote when unsigned · Barber-Odean context, never inverted.
- Strategy badges: heuristic label ("strategy heuristic — incomplete legs possible") · under→ticker,
  exp→expiration mapping exact.
- Gamma/GEX surfaces: OI-signed GEX labeled proxy not DDOI · no GX-as-Ni · no ΓIB-as-Barbon ·
  no flip-as-academic · no crash probability numbers · no -$200mm line.
- ROUND-9: fragility tags must carry qualifiers — "association (not causation), large-cap sample,
  pre/post-2010 regime" (Barbon full text). Bare "fragile" with no qualifier fails the checklist.
- Toxicity/VPIN: user-facing "VPIN" banned unless signed trade-level feed connected; otherwise
  "toxicity proxy (not VPIN)".

**Recommended CI gate:** rg -i for banned phrases across frontend/src + backend user-facing strings.
