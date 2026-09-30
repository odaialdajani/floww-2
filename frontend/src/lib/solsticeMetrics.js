/**
 * solsticeMetrics — the frontend side of the R11 metric display contract.
 *
 * Contract: docs/solstice/r11/METRIC_CONTRACT.md. This module computes NO
 * Greeks. It only (a) names the registered surfaces the backend emits,
 * (b) reads their coverage/status, (c) sums ONE surface's cells over ONE
 * declared expiry scope for a strike profile, and (d) derives a
 * conditional, price-gated wall read from values the backend supplied.
 *
 * Missing is never zero: an unknown value is `null`, a partial cell is
 * flagged, and an unavailable surface carries the backend reason.
 */
import { wallPositionOf } from "./solsticeSelection";

// Primary GEX bases (the compact basis menu inside GEX). Order is the
// trader's workflow: Raw locates the wall (where); the adjusted surfaces
// describe how the exposure at that wall is weighted (how).
export const GEX_BASES = [
  {
    id: "raw", label: "Raw OI", short: "Raw OI", metricId: "gex_net_v1", basis: "OI",
    role: "where", section: null,
    note: "Σ c·u·OI — open-interest gamma per 1% move. Locates structural walls.",
  },
  {
    id: "delta", label: "Δ-weighted OI", short: "Δ-wtd OI", metricId: "dadgex_net_v1",
    basis: "OI_DELTA_WEIGHTED", role: "how", section: "delta",
    note: "OI gamma weighted by |delta|. A weighting, not observed buying or selling.",
  },
  {
    id: "session_delta_volume", label: "Volume × |Δ| activity", short: "Vol×|Δ|",
    metricId: "session_delta_volume_gamma_v1", basis: "VOLUME_DELTA_WEIGHTED", role: "how",
    section: "session_delta_volume",
    note: "Today's session volume gamma weighted by |delta|. Turnover, not new positions.",
  },
];

// Secondary surfaces: still selectable where a comparison needs them, but
// never presented as a primary tab.
export const SECONDARY_BASES = [
  {
    id: "activity", label: "Session volume (no Δ)", short: "Session vol", metricId: "volume_gamma_v1",
    basis: "VOLUME", role: "how", section: "activity",
    note: "Σ c·u·V — session turnover without delta weighting.",
  },
  {
    id: "window", label: "Window Δvol × |Δ|", short: "Window", metricId: "window_dadgex_v1",
    basis: "VOLUME_WINDOW", role: "how", section: "window",
    note: "Change in volume between two comparable observations, weighted by |delta|.",
  },
];

export const ALL_BASES = [...GEX_BASES, ...SECONDARY_BASES];
export const ADJUSTED_BASES = ALL_BASES.filter((b) => b.role === "how");

export function baseDef(id) {
  return ALL_BASES.find((b) => b.id === id) || null;
}

export function strikeKey(s) {
  const n = Number(s);
  if (!Number.isFinite(n)) return String(s);
  return Number.isInteger(n) ? String(n) : String(n);
}

function finite(v) {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** The grid section for a basis, or null when the snapshot lacks it. */
export function sectionFor(data, id) {
  if (!data) return null;
  if (id === "raw") return data.grid || null;
  const def = baseDef(id);
  const sec = def?.section ? data?.metrics?.grids?.[def.section] : null;
  return sec || null;
}

/**
 * Coverage/status for a basis. Prefers the backend's surface_coverage
 * summary; falls back to the section's own status for older packets.
 * Returns {status: ok|partial|unavailable, reason, usable, missing}.
 */
export function surfaceStatus(data, id) {
  const cov = data?.metrics?.surface_coverage?.[id];
  if (cov && typeof cov === "object") {
    return {
      status: cov.status || "unavailable",
      reason: cov.reason || null,
      usable: Number.isInteger(cov.usable) ? cov.usable : null,
      missing: (cov.missing_delta || 0) + (cov.missing_oi || 0) + (cov.missing_inputs || 0),
      invalid: cov.invalid || 0,
    };
  }
  const sec = sectionFor(data, id);
  const g = id === "raw" ? sec?.grid : sec?.grid;
  if (!sec || !g || !Object.keys(g).length) {
    return { status: "unavailable", reason: sec?.reason || "not in this snapshot", usable: null, missing: 0, invalid: 0 };
  }
  const missing = Number(sec.missing_delta) || 0;
  return { status: missing > 0 ? "partial" : "ok", reason: null, usable: null, missing, invalid: 0 };
}

/**
 * Signed strike profile for ONE surface over ONE declared expiry scope.
 * Sums only that surface's own cells (no Greek arithmetic). A strike with
 * no cell in any scoped expiry is null (gap), never 0. `partial` marks
 * strikes where the backend excluded contracts for unknown delta.
 */
export function sumProfile(data, id, scopeExpiries) {
  const sec = sectionFor(data, id);
  const grid = sec?.grid;
  const out = { id, values: {}, partial: {}, maxAbs: 0, available: !!(grid && Object.keys(grid).length) };
  if (!out.available) return out;
  const exps = (scopeExpiries && scopeExpiries.length ? scopeExpiries : Object.keys(grid));
  const miss = sec.cell_missing_delta || {};
  for (const e of exps) {
    const col = grid[e];
    const mcol = miss[e] || {};
    if (col) {
      for (const k of Object.keys(col)) {
        const v = finite(col[k]);
        if (v == null) continue;
        out.values[k] = (out.values[k] || 0) + v;
      }
    }
    for (const k of Object.keys(mcol)) {
      if (mcol[k] > 0) out.partial[k] = (out.partial[k] || 0) + mcol[k];
    }
  }
  for (const v of Object.values(out.values)) out.maxAbs = Math.max(out.maxAbs, Math.abs(v));
  return out;
}

/** Same-wall values for every family, each with its own coverage. */
export function wallValues(data, wall) {
  if (!wall) return null;
  const wb = data?.metrics?.wall_metrics?.[wall.wall_id || ""] || null;
  const ww = data?.metrics?.wall_window?.[wall.wall_id || ""] || null;
  const cnt = (v) => (Number.isInteger(v) && v >= 0 ? v : null);
  return {
    raw: { gross: finite(wall.gross), net: finite(wall.net), usable: null, missing: 0 },
    delta: wb ? {
      gross: cnt(wb.daddex_usable) ? finite(wb.daddex_gross) : null,
      net: cnt(wb.daddex_usable) ? finite(wb.daddex_net) : null,
      usable: cnt(wb.daddex_usable), missing: cnt(wb.daddex_missing) || 0,
    } : null,
    session_delta_volume: wb && Object.prototype.hasOwnProperty.call(wb, "sdv_net") ? {
      gross: cnt(wb.sdv_usable) ? finite(wb.sdv_gross) : null,
      net: cnt(wb.sdv_usable) ? finite(wb.sdv_net) : null,
      usable: cnt(wb.sdv_usable), missing: cnt(wb.sdv_missing_delta) || 0,
    } : null,
    activity: wb ? {
      gross: cnt(wb.volume_usable) ? finite(wb.volume_gross) : null,
      net: cnt(wb.volume_usable) ? finite(wb.volume_net) : null,
      usable: cnt(wb.volume_usable), missing: cnt(wb.volume_missing) || 0,
    } : null,
    window: ww ? { gross: null, net: finite(ww.window_daddex), usable: cnt(ww.coverage?.active_strikes), missing: 0 } : null,
  };
}

// Display policy (not a forecast): an adjusted net smaller than this share
// of the wall's raw gross is shown as "near zero — two-sided", not signed.
export const NEAR_ZERO_SHARE = 0.05;

/**
 * Conditional wall read: raw locates, the chosen adjusted surface's SIGN
 * at the same wall names which WATCH applies, and measured price
 * interaction controls readiness. Never an order, never a target/stop,
 * never a statement about dealer intent.
 *
 *   adjusted > 0 (dampening):  wall below price → Bounce watch
 *                              wall above price → Rejection watch
 *   adjusted < 0 (amplifying): wall below price → Downside continuation watch
 *                              wall above price → Upside continuation watch
 */
export function wallRead({ wall, spot, adjNet, adjAvailable, rawGross, interaction, quality }) {
  const pos = wallPositionOf(wall, spot);
  const reasons = [];
  let watch = null;
  let tone = "neutral";
  if (!wall) return { watch: null, tone, readiness: "Observe", reasons: ["no wall selected"], position: pos };
  if (!adjAvailable || adjNet == null) {
    reasons.push("adjusted value unavailable at this wall — no read from raw sign alone");
  } else if (rawGross != null && rawGross > 0 && Math.abs(adjNet) < NEAR_ZERO_SHARE * rawGross) {
    reasons.push(`adjusted net near zero (< ${Math.round(NEAR_ZERO_SHARE * 100)}% of raw gross) — two-sided`);
    tone = "flat";
  } else if (pos === "unknown") {
    reasons.push("spot unknown — position relative to wall cannot be stated");
  } else if (pos === "inside") {
    watch = adjNet > 0 ? "Inside zone · dampening" : "Inside zone · amplifying";
    tone = adjNet > 0 ? "positive" : "negative";
    reasons.push("price inside the wall — wait for hold vs acceptance beyond");
  } else if (adjNet > 0) {
    watch = pos === "below" ? "Bounce watch" : "Rejection watch";
    tone = "positive";
  } else {
    watch = pos === "below" ? "Downside continuation watch" : "Upside continuation watch";
    tone = "negative";
  }
  const state = interaction?.state || "unobserved";
  const eligible = quality?.setupEligible === true;
  let readiness = "Observe";
  if (state === "invalidated" || state === "expired") readiness = "Invalidated";
  else if (!eligible) {
    readiness = "Wait";
    reasons.push((quality?.reasonCodes || [])[0] || "data quality blocks review");
  } else if (!watch) readiness = "Wait";
  else if (["holding", "rejecting", "accepted_beyond"].includes(state)) readiness = "Confirmed for review";
  else reasons.push(state === "unobserved" ? "awaiting measured price interaction" : `watching (${state})`);
  return { watch, tone, readiness, reasons, position: pos };
}

export function fmtUsdCompact(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(1)}K`;
  return `${sign}$${a.toFixed(0)}`;
}
