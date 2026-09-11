# Proposal packet: persistence-backed signals (Amihud / Roll / Hawkes)

Lane: Tidehunter (Agent 3). Read-only proposals — no backend edits.
Math sources: wave-2 research (`/tmp/wf_wave2_{cost,0dte,flow}.md`), synthesis
`reports/tidehunter-wave2-synthesis.md`. Frontend engine already shipped and
tested (scanLogic: rollSpread/rollPooled/pushCapped, skewLevels, pinRisk).

## A. Amihud daily ILLIQ store (downgraded SHIP → FIXTURE-FIRST, correctly)

- Math: ILLIQ = mean(|r_d| / DV_d) over D=5/20 days; display log1p +
  1/99 winsorize + cross-sectional rank within expiry (raw level is
  scale noise on options DV).
- Needs: daily close + day-volume per contract (B1 daily persistence;
  the 50-snapshot intraday cap cannot supply it).
- Fixture: zero-vol days dropped not zeroed; tiny-DV winsorize caps;
  rank stability across two consecutive sessions on fixtures.
- OpenAPI sketch: `GET /api/liquidity/{ticker}/amihud-daily?window=20` →
  `{ illiq, rank, n, window, asof }`, 200 + `stale:true` when the
  daily job hasn't run (never 503 — structured-empty rule).

## B. Roll persistence (frontend session rings exist; backend rollup is B1)

- Frontend ships session rings (cap 60) + pooled bucket + building gate.
- Backend: persist 15s mids per contract per day; endpoint
  `GET /api/microstructure/roll/{ticker}?exp=YYYY-MM-DD` →
  `{ spread, nd, truncated, building, window }`.
- Fixture (mirror frontend Jest): synthetic bounce recovers known s;
  flat/trend truncates to 0 with flag; <30 deltas → building, never a number.

## C. Hawkes calibration gate (backend module exists, uncalibrated use is banned)

- `hawkes_process.py` (exp + power-law) ships as heuristic burst tag only.
- Gate: expose calibrated `eta` behind `calibrated:true` ONLY when the
  fit window holds ≥200 events AND eta<1 (cap 0.9); else heuristic label.
- Endpoint: extend existing `GET /api/hawkes/{ticker}/state` with
  `{ calibrated, eta }` — no new route.
- Fixture: bursty synthetic windows must not explode past the cap.

## Key discipline (architect law, verified this session)

- No new per-ticker Public pollers from any wave: COST/PIN/drift/skew all
  read existing signals state. Chain data only via the cached
  `fetch_chain_from_public_api` path (`/public/chain`, backend-cached).
- Endpoint verification status: backend :8000 down all session (binds,
  never serves; PID churn) — every endpoint claim above is code-read
  (server.py mounts confirmed for liquidity/hawkes/microstructure), NOT
  live-curled. Re-verify with live curl before building any consumer.
