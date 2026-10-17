/**
 * triadProjection — canonical Public chain -> Triad data packet.
 *
 * WHY THIS EXISTS
 * ===============
 * The Triad view used to build its own rows and grid inline. That inline
 * transform had six defects, each reproduced in the audit:
 *
 *   1. The grid was keyed by (expiry, strike) with NO side dimension, so a
 *      call and a put at the same strike wrote the same slot and the last
 *      one won. A +100 call and a -60 put became -60 — the call's exposure
 *      was silently destroyed rather than netted.
 *   2. `contracts.slice(0, 200)` dropped the tail with no record.
 *   3. `c.expiry || "2026-09-18"` invented an expiry for contracts that had
 *      none, which then rendered as a real column.
 *   4. `{ grid: { "0": {} } }` seeded a literal "0" expiry. The grid takes
 *      the first 6 sorted expiry keys, and "0" sorts before every date, so
 *      that placeholder consumed a column and pushed out a real expiry.
 *   5. `vex: 0` recorded an UNMEASURED Greek as a measured zero.
 *   6. `change_pct: 0` and `vix: 20` invented market state.
 *
 * Every one of those is a number that looks like data. This module derives
 * the same packet from the same input while keeping unknown values unknown.
 *
 * CONTRACT
 * ========
 * Input is the `/api/public/chain/{ticker}` payload. Its `gex` field is
 * already signed by the backend (`services.chain_readings`: calls positive,
 * puts negative) and is the ONLY exposure field this module trusts.
 *
 * Output cells and rows carry `null` for anything the input did not
 * measure. `null` renders as an em dash in this UI, which is the honest
 * display for "not observed". A metric is never defaulted to 0.
 */

export const TRIAD_PROJECTION_VERSION = "triad-projection.v1";

/** Per-side keys that must never be silently blended across call and put. */
const SIDE_FIELDS = ["iv", "delta", "gamma", "vega", "theta", "vanna", "charm", "bid", "ask"];

function num(value) {
  if (value === null || value === undefined || typeof value === "boolean") return null;
  const out = typeof value === "number" ? value : Number(value);
  return Number.isFinite(out) ? out : null;
}

function sideOf(contract) {
  const type = String(contract?.type ?? "").trim().toLowerCase();
  if (type.startsWith("c")) return "call";
  if (type.startsWith("p")) return "put";
  // An unlabelled contract cannot be assigned a sign, so it cannot be
  // aggregated into an exposure total without inventing one.
  return null;
}

function strikeKey(strike) {
  return String(strike);
}

/**
 * Aggregate one (expiry, strike) cell from the contracts that belong to it.
 *
 * Exposure (`gex`) is additive and signed, so it sums. Per-side Greeks are
 * NOT additive across a call and a put at the same strike, so they are kept
 * per side and the blended field is null unless exactly one side is present.
 */
function aggregateCell(contracts, spot) {
  const sides = { call: null, put: null };
  let gex = null;
  let gexCall = null;
  let gexPut = null;
  let missingGex = 0;
  let unlabelled = 0;
  let oi = null;
  let volume = null;

  for (const c of contracts) {
    const side = sideOf(c);
    if (side === null) {
      unlabelled += 1;
      continue;
    }
    const value = num(c.gex);
    if (value === null) {
      // Unknown exposure contributes nothing. It is counted so the caller
      // can explain the gap instead of showing a zero that looks measured.
      missingGex += 1;
    } else {
      gex = (gex ?? 0) + value;
      if (side === "call") gexCall = (gexCall ?? 0) + value;
      else gexPut = (gexPut ?? 0) + value;
    }
    const cOi = num(c.oi ?? c.open_interest);
    if (cOi !== null) oi = (oi ?? 0) + cOi;
    const cVol = num(c.volume);
    if (cVol !== null) volume = (volume ?? 0) + cVol;
    if (sides[side] === null) sides[side] = c;
  }

  const present = [sides.call, sides.put].filter(Boolean);
  const cell = {
    gex,
    call_gex: gexCall,
    put_gex: gexPut,
    oi,
    volume,
    strike_exact: contracts.find(Boolean)?.strike_exact ?? null,
    missing_gex: missingGex,
    unlabelled: unlabelled,
    sides_present: present.length,
  };
  for (const field of SIDE_FIELDS) {
    // One side only -> the value is unambiguous. Both sides -> blending two
    // different Greeks into one number would be a fabrication, so null it.
    if (present.length === 1) {
      cell[field] = num(present[0][field]);
    } else {
      cell[field] = null;
      cell[`call_${field}`] = num(sides.call?.[field]);
      cell[`put_${field}`] = num(sides.put?.[field]);
    }
  }
  // `vex` is a distinct Greek. The input carries no vanna exposure measurement,
  // so it stays unknown rather than zero-filled.
  cell.vex = null;
  void spot;
  return cell;
}

/** Build the per-strike rows the DOM / bars / chain views consume. */
function buildRows(cellsByStrike, expiries) {
  const rows = [];
  for (const [key, perExpiry] of cellsByStrike) {
    const cellList = expiries
      .map((exp) => perExpiry.get(exp))
      .filter(Boolean);
    if (!cellList.length) continue;
    const row = {
      strike: Number(key),
      gex: null,
      call_gex: null,
      put_gex: null,
      oi: null,
      total_oi: null,
      volume: null,
      expiries: [...perExpiry.keys()].sort(),
      cells_present: cellList.length,
    };
    for (const cell of cellList) {
      for (const field of ["gex", "call_gex", "put_gex", "oi", "volume"]) {
        if (cell[field] === null) continue;
        row[field] = (row[field] ?? 0) + cell[field];
      }
    }
    row.total_oi = row.oi;
    // A strike row spans multiple expiries, so a single IV/Delta/Gamma for it
    // does not exist. Per-expiry values live in the grid cells.
    for (const field of SIDE_FIELDS) row[field] = null;
    row.dte = perExpiry.values().next().value?.dte ?? null;
    row.expiry = row.expiries.length === 1 ? row.expiries[0] : null;
    rows.push(row);
  }
  return rows.sort((a, b) => b.strike - a.strike);
}

/**
 * Project a `/api/public/chain` payload into the Triad data packet.
 *
 * `expiryCount` is an EXPIRY COUNT, not a DTE window. The two are reported
 * separately (`coverage.expiries_requested` vs each cell's `dte`) because
 * the previous labels ("0-1DTE", "~3DTE", "1 Week") described a day window
 * while the value sent to the API selected a number of expirations.
 */
export function projectTriadFromChain(payload, options = {}) {
  const { expiryCount = null } = options;
  const contracts = Array.isArray(payload?.contracts) ? payload.contracts : [];
  const requested = num(payload?.coverage?.requested) ?? num(payload?.n_contracts) ?? contracts.length;

  const dropped = { no_expiry: 0, bad_strike: 0, unknown_side: 0, no_gex: 0 };
  const byExpiry = new Map();

  for (const c of contracts) {
    if (!c || typeof c !== "object") {
      dropped.bad_strike += 1;
      continue;
    }
    const strike = num(c.strike);
    if (strike === null || strike <= 0) {
      dropped.bad_strike += 1;
      continue;
    }
    const expiry = typeof c.expiry === "string" ? c.expiry.trim() : "";
    if (!expiry) {
      // Never substitute a date. A contract with no expiry cannot be placed
      // in a time column, and a fabricated one renders as a real expiry.
      dropped.no_expiry += 1;
      continue;
    }
    if (sideOf(c) === null) {
      dropped.unknown_side += 1;
      continue;
    }
    if (!byExpiry.has(expiry)) byExpiry.set(expiry, new Map());
    const perStrike = byExpiry.get(expiry);
    const key = strikeKey(strike);
    if (!perStrike.has(key)) perStrike.set(key, []);
    perStrike.get(key).push(c);
  }

  const allExpiries = [...byExpiry.keys()].sort();
  const cap = num(expiryCount);
  const capApplied = cap !== null && cap > 0 && allExpiries.length > cap;
  const expiries = capApplied ? allExpiries.slice(0, cap) : allExpiries;

  const spot = num(payload?.spot);
  // cellsByStrike: strike -> (expiry -> cell)
  const cellsByStrike = new Map();
  const grid = {};
  for (const exp of expiries) {
    grid[exp] = {};
    for (const [key, group] of byExpiry.get(exp)) {
      const cell = aggregateCell(group, spot);
      grid[exp][key] = cell;
      if (cell.gex === null) dropped.no_gex += cell.missing_gex;
      if (!cellsByStrike.has(key)) cellsByStrike.set(key, new Map());
      cellsByStrike.get(key).set(exp, cell);
    }
  }

  const rows = buildRows(cellsByStrike, expiries);
  const netGex = rows.reduce((sum, r) => sum + (r.gex ?? 0), 0);
  // King is a STRIKE, chosen from aggregated strike rows — not a single
  // contract, which is what the previous inline reduce returned.
  let king = null;
  for (const row of rows) {
    const v = Math.abs(row.gex ?? 0);
    if (king === null || v > Math.abs(king.gex ?? 0)) king = { strike: row.strike, gex: row.gex };
  }

  const measured = rows.filter((r) => r.gex !== null).length;
  return {
    projection_version: TRIAD_PROJECTION_VERSION,
    ticker: payload?.ticker ?? null,
    spot,
    // Not provided by this input. Unknown, never defaulted to a number.
    change_pct: null,
    vix: null,
    nodes: {
      regime: netGex > 0 ? "positive" : netGex < 0 ? "negative" : "neutral",
      king,
      // The zero-gamma root is a backend computation. Inferring a root from
      // adjacent strike buckets changing sign is not that computation.
      gamma_flip: null,
      floors: [],
      ceilings: [],
      gatekeepers: [],
      air_pockets: [],
      // "polarity" is not |exposure| / spot. Reported unknown rather than
      // inventing a normalized number.
      polarity_level: null,
      net_gex: rows.length ? netGex : null,
    },
    strikes: rows,
    grid: { grid },
    expiries_used: expiries,
    coverage: {
      requested,
      returned: contracts.length,
      usable: measured,
      dropped_no_expiry: dropped.no_expiry,
      dropped_bad_strike: dropped.bad_strike,
      dropped_unknown_side: dropped.unknown_side,
      contracts_without_gex: dropped.no_gex,
      expiries_available: allExpiries.length,
      expiries_requested: cap,
      expiries_used: expiries.length,
      // Declared, never silent. The grid cap is a display decision that the
      // caller can surface; it is not a data-cleaning step.
      expiry_cap_applied: capApplied,
      expiries_dropped_by_cap: capApplied ? allExpiries.length - cap : 0,
      truncated: capApplied,
    },
    data_source: payload?.data_source ?? "public_api",
    stale: payload?.stale === true,
  };
}

export default projectTriadFromChain;



