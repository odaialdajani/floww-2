# PROPOSAL (apply-blind): B3 FINRA ATS + Reg SHO dark-pool context ETL

Status: PROPOSAL-ONLY. Owner lane: architect/backend.

## 0. Verify first (parsers depend on it — do not guess layouts)
1. Confirm current FINRA ATS weekly block-data file URL + column layout
   (ticker, venue/MPID, shares, week-ending) from the FINRA ATS
   transparency page.
2. Confirm Reg SHO daily short-volume file URL + columns
   (date, ticker, short volume, total volume) from FINRA Reg SHO page.
3. If either source moved/paywalled: ship the endpoint as explicit
   `unavailable` + reason (never a live tape on free data — desk rule).

## 1. Design
- Job: weekly ATS pull (Tue, after Monday publish) + daily SHO pull
  (evening), same `asyncio.create_task(_logged_task(...))` precedent
  as B1. Keyless plain-HTTPS downloads; store raw files by date for
  audit before parsing.
- Mongo: `dark_ats_weekly {ticker, venue, shares, week_ending,
  source_ts}` index (ticker, week_ending); `regsho_daily {ticker,
  date, short_volume, total_volume, source_ts}` index (ticker, date).
- Panel math: venue-share by ticker for latest week; short-pressure =
  short_volume/total_volume (a pressure proxy — NO directional claim,
  enforced in copy).
- Dark Top-N levels: ONLY from legally free historical prints if a
  source verifies in step 0; otherwise the field is explicit
  `{available: false, reason}` — never synthesized.
- Stale: every response carries `asof` + `stale` (weekly cadence =
  stale is normal, not an error).

## 2. Fixture (pytest sketch, checked-in sample files)
- 2-row ATS sample + 2-row SHO sample in `fixtures/backend/` →
  venue-share math + pressure proxy asserted; malformed row →
  skipped + counted, never fatal.
- Missing week → `stale: true` with last good `asof`, 200.

## 3. OpenAPI sketch
- `GET /api/darkpool/context/{ticker}` → `{ ats: {venue_share,
  week_ending}, sho: {short_pressure, date}, levels: {available,
  reason?}, asof, stale }`.

## 4. Acceptance
Copy audit: zero directional verbs in responses/docs; 30-day paper run
with no missed weeks unexplained in the status row.
