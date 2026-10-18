import React, { memo } from "react";
import { explainWall } from "../../lib/solsticeExplain";
import "./ReviewInspector.css";

/**
 * WallInspector — selected-wall inspector (T07 §28.3): Now / Changed /
 * Confirm / Invalidates + data quality. Shows gross/net/call/put with units
 * and basis, per-expiry contributions, magnitude ratio, pair provenance and
 * OI-effective-date coverage. Deterministic template; optional AI prose
 * deepens it but never replaces numbers. Unknown/no-data are first-class.
 */
function Row({ k, v, tip }) {
  return (
    <div className="skylit-metric-row" title={tip || undefined}>
      <span className="skylit-metric-label">{k}</span>
      <span className="skylit-metric-value">{v ?? "—"}</span>
    </div>
  );
}

function fmtUsd(v) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(1)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

function memberStrikes(wall) {
  return [...new Set((Array.isArray(wall?.members) ? wall.members : [])
    .filter(s=>typeof s==="number" || (typeof s==="string" && s.trim()!==""))
    .map(Number).filter(s=>Number.isFinite(s) && s>0))];
}
function usableCount(value) {
  return typeof value==="number" && Number.isSafeInteger(value) && value>=0 ? value : null;
}
function windowReason(metrics) {
  // Canonical spelling wins, including null on a valid current window.
  return Object.hasOwn(metrics || {}, "window_dadgex_reason")
    ? metrics.window_dadgex_reason : metrics?.window_daddex_reason;
}

// ── Shared same-wall breakdown semantics (2026-10-17) ─────────────────
// One source for the compact FocusSummary and the deeper CompareTable so
// the two cannot drift. Missing is "—", never zero (R8-06: a zero with
// no usable inputs is missing data, not a measured zero); usable counts
// only recognize safe non-negative integers.
function fmtCell(v) {
  return v == null ? "—" : fmtUsd(v);
}

function wallDeltaWeighted(wb) {
  const usable = usableCount(wb?.daddex_usable);
  const missing = usableCount(wb?.daddex_missing);
  const invalid = usableCount(wb?.daddex_invalid);
  const absentNote = [missing > 0 ? `${missing} δ-missing` : null,
    invalid > 0 ? `${invalid} δ-invalid (unusable reading)` : null].filter(Boolean).join(", ");
  const value = !wb ? "—"
    : usable > 0 ? `${fmtCell(wb.daddex_gross)} / ${fmtCell(wb.daddex_net)}`
    : absentNote ? `— (${absentNote})` : "—";
  return { value, usable, missing, invalid, absentNote };
}

function wallSessionVolume(wb) {
  const usable = usableCount(Object.hasOwn(wb || {}, "volume_usable") ? wb.volume_usable : wb?.volume_n);
  const missing = usableCount(wb?.volume_missing);
  const invalid = usableCount(wb?.volume_invalid);
  const value = !wb ? "—"
    : usable > 0 ? `${fmtCell(wb.volume_gross)} / ${fmtCell(wb.volume_net)}` : "—";
  return { value, usable, missing, invalid };
}

function wallSessionDeltaVolume(wb) {
  const usable = usableCount(wb?.session_delta_volume_usable);
  const missing = usableCount(wb?.session_delta_volume_missing);
  const invalid = usableCount(wb?.session_delta_volume_invalid);
  const value = usable > 0
    ? `${fmtCell(wb.session_delta_volume_gross)} / ${fmtCell(wb.session_delta_volume_net)}` : "—";
  return { value, usable, missing, invalid };
}

function wallRecentWindow(wallWin, metrics) {
  // R6-2: wall-local window Δ-activity over member strikes with member/active
  // coverage; the whole-scope window scalar is never shown as wall-local.
  // Absence reports its reason — a missing window is never zero. Shared by
  // the compact FocusSummary and CompareTable so the wording cannot drift.
  const cov = (wallWin && wallWin.coverage) || {};
  const reason = windowReason(metrics);
  const value = wallWin
    ? `${fmtUsd(wallWin.window_daddex)} · ${cov.active_strikes ?? "—"}/${cov.member_strikes ?? "—"} strikes`
    : (reason === "VOLUME_REBASE"
      ? "unavailable — volume rebase"
      : `unavailable — ${reason || "no comparable window"}`);
  return { value, reason, present: Boolean(wallWin) };
}

function WallInspector({ wall = null, interaction = null, metrics = null, grids = null, displayGrid = null, quality = null, scenario = null, goneReason = null, lastWallId = null,
  scout = null, patterns = null, regime = null, vanna = null, moneyness = null,
  metric = "raw", snapshotId = null, replay = false }) {
  if (!wall) {
    if (goneReason === "WALL_GONE") {
      return (
        <div className="skylit-metrics-section" data-testid="wall-inspector-gone">
          <div className="skylit-section-title">Selected wall · gone</div>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>Wall {lastWallId || ""} is not in this snapshot — no nearby substitute selected. Last observation retained in history.</div>
        </div>
      );
    }
    return (
      <div className="skylit-metrics-section" data-testid="wall-inspector-empty">
        <div className="skylit-section-title">Selected wall</div>
        <div style={{ fontSize: 12, color: "#94a3b8" }}>Select a cell to inspect its wall.</div>
      </div>
    );
  }
  const members = memberStrikes(wall);
  // Per-expiry contributions for member strikes from the same snapshot grids.
  const perExpiry = [];
  if (grids) {
    const seen = new Set();
    for (const [name, g] of Object.entries(grids)) {
      if (!g || !g.grid) continue;
      for (const [exp, col] of Object.entries(g.grid)) {
        let sum = 0;
        let hit = false;
        for (const s of members) {
          const k = Number.isInteger(s) ? String(s) : String(s);
          if (typeof col?.[k] === "number" && Number.isFinite(col[k])) { sum += col[k]; hit = true; }
        }
        if (hit && !seen.has(`${name}|${exp}`)) {
          seen.add(`${name}|${exp}`);
          perExpiry.push({ grid: name, expiry: exp, value: sum });
        }
      }
    }
  }
  const ratio = metrics?.magnitude_ratio_delta_over_raw;
  // R8-06 blend: group by grid surface when uniform so the row reads
  // "delta 09-28 $1.1M · 09-29 $2.2M" instead of repeating the prefix.
  const perExpiryGroups = (() => {
    const shown = perExpiry.slice(0, 6);
    const names = [...new Set(shown.map((p) => p.grid))];
    if (names.length === 1) {
      return `${names[0]} ` + shown.map((p) => `${p.expiry.slice(5)} ${fmtUsd(p.value)}`).join(" · ");
    }
    return shown.map((p) => `${p.grid}:${p.expiry.slice(5)}=${fmtUsd(p.value)}`).join(" · ");
  })();
  const pairNote = metrics
    ? `Δ usable ${metrics.dadgex_usable ?? "—"}, missing ${metrics.dadgex_missing_delta ?? "—"}`
    : "—";
  // R6-2 wall-local window activity: aggregate over THIS wall's member
  // strikes only (with member/active coverage). The whole-scope sum is never
  // shown as wall-local; without a comparable baseline the row reports why.
  // (Shared helper with the compact FocusSummary and the CompareTable row —
  // one wall-local window value, never the scope scalar.)
  const wallWin = (metrics?.wall_window || {})[wall.wall_id || ""];
  const winReason = windowReason(metrics);
  // R6-2 same-wall comparison: raw (wall record), delta-weighted and session
  // activity (wall_metrics breakdown). Each declares its basis; unlike
  // quantities are never blended and scope totals stay out of this table.
  const wb = (metrics?.wall_metrics || {})[wall.wall_id || ""];
  return (
    <div className="skylit-metrics-section" data-testid="wall-inspector">
      <div className="skylit-section-title">Selected wall · {wall.wall_id || `${wall.low}–${wall.high}`}</div>
      {/* Identity line (2026-10-18 reconciliation): the wall's zone, basis
          and OI effective date stay visible while the Now row moves, so
          identity never depends on the disclosure. Walls span expiries; the
          selected expiry remains visible in ReviewSelectionContext. Nothing
          here is invented: an absent wall formula states it is unavailable,
          and this date is named as the OI effective date, never as expiry. */}
      <div className="wall-identity-line" data-testid="wall-identity-line">
        {wall.low}–{wall.high} · basis {wall.exposure_basis || "OI"}
        {" · "}Formula {wall.formula_version || "unavailable"}
        {" · "}OI date {(Array.isArray(wall.oi_effective_dates) && wall.oi_effective_dates.length) ? wall.oi_effective_dates.join(", ") : "unavailable"}
      </div>
      <FocusSummary wall={wall} wb={wb} wallWin={wallWin} metrics={metrics} />
      {/* Always visible: readiness, confirmation, invalidation and explicit
          data quality. Repeated supporting facts and interaction history live
          in the Exposure details disclosure below — accessible, never dropped. */}
      <Readiness interaction={interaction} quality={quality} scenario={scenario} />
      <Row k="Confirm" v={scenario?.confirmation || "Confirmation not supplied — observe, not an entry signal"} />
      <Row k="Invalidates" v={scenario?.invalidation || "Invalidation not supplied — no trade plan inferred"} />
      <Row k="Data" v={quality ? `${quality.state || "unknown"} · ${(quality.reasonCodes || []).join(", ") || "ok"}` : "unknown"} />
      <details className="wall-exposure-details" data-testid="wall-exposure-details">
      <summary>Exposure details and coverage</summary>
      <div className="wall-details-section" data-testid="wall-details-facts">
        <div className="wall-details-heading">Wall facts</div>
        <Row k="Now" v={`${wall.low}–${wall.high} · gross ${fmtUsd(wall.gross)} · net ${fmtUsd(wall.net)} (USD/1% move, ${wall.exposure_basis || "OI"})`} />
        <Row k="Call / Put" v={`${fmtUsd(wall.call)} / ${fmtUsd(wall.put)}`} tip="Call-plus vs put-minus components; high gross + near-zero net is two-sided concentration" />
        <Row k="Distance" v={wall.distance != null ? `${Number(wall.distance).toFixed(2)} (${(Number(wall.distance_pct) * 100).toFixed(2)}%)` : "—"} />
      </div>
      <div className="wall-details-section" data-testid="wall-details-interaction">
        <div className="wall-details-heading">Interaction history</div>
        <Row k="Changed" v={interaction ? `${interaction.state}${interaction.event ? ` · ${interaction.event}` : ""}${interaction.first_seen === false ? " · persistent" : " (first sighting — see replay compare)"}${interaction.durable === true ? " · durable" : interaction.durable === false ? " · memory-only" : ""}` : "see replay compare"} tip="Wall-level change needs 2+ recorded snapshots; persistent states carry continuity, first sightings do not; durable = restored from DuckDB after restart, memory-only = in-process" />
        <InteractionTimeline interaction={interaction} />
        <Row k="Interaction" v={interaction ? interaction.state : "unobserved"} tip="Time-debounced state machine; session/feed gaps break continuity" />
        <Row k="Touches" v={interaction && interaction.taps != null ? String(interaction.taps) : "unknown — no history"} tip="Observed touches only; never a calibrated probability" />
      </div>
      <div className="wall-details-section" data-testid="wall-details-coverage">
        <div className="wall-details-heading">Coverage and provenance</div>
        {perExpiry.length > 0 && (
          <Row k="Per-expiry" v={perExpiryGroups} tip="Same-snapshot per-expiry contributions for member strikes" />
        )}
        <Row k="Δ/Raw (scope)" v={ratio != null ? Number(ratio).toFixed(3) : "—"} tip="Scope-wide delta gross / raw gross over the same snapshot set — not the selected wall. Wall-local ratio needs same-wall delta + raw grids." />
        <CompareTable wall={wall} metrics={metrics} displayGrid={displayGrid} />
        <Row k="Δ provenance" v={pairNote} tip="Vendor/vendor, local/local eligible; mixed pairs blocked without policy" />
        <Row k="OI eff. date" v={(wall.oi_effective_dates && wall.oi_effective_dates.length ? wall.oi_effective_dates.join(", ") : null) ?? "unavailable in snapshot"} tip="Per-wall OI effective dates from member-strike provenance; unavailable when no member carries OI metadata" />
      </div>
      </details>
      <ExplainThisWall
        snapshotId={snapshotId} wall={wall} metric={metric} replay={replay}
        interaction={interaction} scenarios={scenario ? [scenario] : []} quality={quality}
        wallWindow={wallWin || null} windowReason={winReason || null}
      />
      <ContextSections scout={scout} patterns={patterns} regime={regime} vanna={vanna} moneyness={moneyness} members={members} />
    </div>
  );
}


/**
 * FocusSummary — compact always-visible same-wall summary (2026-10-17
 * focused-context slice): raw OI, OI × |Δ| and session volume × |Δ|
 * gross/net with declared bases and usable/missing/invalid coverage.
 * Wall-local only — scope totals and other walls stay out (the deeper
 * CompareTable keeps the full breakdown). Sign convention is the declared
 * call-positive/put-negative weighting, never a measured dealer reaction;
 * the volume family is not trade-signed flow and nothing here is an entry.
 */
function FocusSummary({ wall, wb, wallWin, metrics }) {
  const d = wallDeltaWeighted(wb);
  const dv = wallSessionDeltaVolume(wb);
  const win = wallRecentWindow(wallWin, metrics);
  const bases = (wb && typeof wb.bases === "object" && wb.bases) || {};
  const contracts = usableCount(wb?.n_contracts);
  const dCov = [
    `usable ${d.usable ?? "unknown"}`,
    d.missing > 0 ? `${d.missing} δ-missing` : null,
    d.invalid > 0 ? `${d.invalid} δ-invalid` : null,
  ].filter(Boolean).join(" · ");
  const dvCov = [
    `usable ${dv.usable ?? "unknown"}`,
    dv.missing > 0 ? `${dv.missing} missing` : null,
    dv.invalid > 0 ? `${dv.invalid} invalid` : null,
  ].filter(Boolean).join(" · ");
  // 2026-10-18 author-review residual: the raw chip must never hardcode a
  // basis the wall record didn't declare. The raw wall input contract defaults
  // to OI only when the record predates the basis field — the same rule the
  // header identity line uses. (The legacy "gex.v2" in the meta below stays:
  // it ships with the accepted 4-chip slice and can only be retired with the
  // formula contract owner, not by relabeling here.)
  const rawBasis = wall.exposure_basis || "OI";
  return (
    <div data-testid="wall-focused-context" className="wall-focused-context">
      <div className="wall-focused-heading">Same wall · gross / net · USD/1% move</div>
      <div className="wall-focused-chip" data-testid="wall-focused-raw">
        <span className="wall-focused-label">Raw {rawBasis}</span>
        <span className="wall-focused-value">{fmtCell(wall.gross)} / {fmtCell(wall.net)}</span>
        <span className="wall-focused-meta">
          USD/1% move · {rawBasis} · gex.v2{contracts != null ? ` · ${contracts} contracts` : ""}
        </span>
      </div>
      <div className="wall-focused-chip" data-testid="wall-focused-delta">
        <span className="wall-focused-label">OI × |Δ|</span>
        <span className="wall-focused-value">{d.value}</span>
        <span className="wall-focused-meta">
          {wb ? `${bases.daddex || "OI_DELTA_WEIGHTED"} · ${dCov}` : "no wall breakdown"}
        </span>
      </div>
      <div className="wall-focused-chip" data-testid="wall-focused-voldelta">
        <span className="wall-focused-label">Vol × |Δ|</span>
        <span className="wall-focused-value">{dv.value}</span>
        <span className="wall-focused-meta">
          {wb ? `${bases.session_delta_volume || "VOLUME_DELTA_WEIGHTED"} · ${dvCov} · not trade-signed flow` : "no wall breakdown"}
        </span>
      </div>
      <div className="wall-focused-chip" data-testid="wall-focused-window">
        <span className="wall-focused-label">Window activity</span>
        <span className="wall-focused-value">{win.value}</span>
        <span className="wall-focused-meta">window Δ-weighted · member coverage · wall-local</span>
      </div>
    </div>
  );
}


/**
 * CompareTable — R7-05 small same-wall comparison table (replaces the long
 * compressed string): raw gross/net, delta gross/net, VEX gross/net,
 * session activity and recent-window activity. Same member contracts and
 * snapshot; each row declares basis/coverage; missing is "—", never zero.
 */
function CompareTable({ wall, metrics, displayGrid }) {
  const members = memberStrikes(wall);
  const wb = (metrics?.wall_metrics || {})[wall.wall_id || ""];
  const wallWin = (metrics?.wall_window || {})[wall.wall_id || ""];
  // Wall-local VEX from the canonical surface (same members, same snapshot).
  let vexNet = null;
  let vexGross = null;
  let vexHit = 0;
  const vexSection = displayGrid?.vex_grid;
  const vexMembers = new Set();
  if (vexSection && members.length) {
    vexNet = 0;
    vexGross = 0;
    for (const col of Object.values(vexSection)) {
      for (const s of members) {
        const k = Number.isInteger(s) ? String(s) : String(s);
        const v = col ? col[k] : null;
        if (typeof v === "number" && Number.isFinite(v)) {
          vexNet += v;
          vexMembers.add(Number(s));
          vexHit += 1;
        }
      }
    }
    if (!vexHit) {
      vexNet = null;
      vexGross = null;
    }
  }
  // Gross is the sum of absolute CONTRACT contributions, not absolute net
  // cells (calls and puts can offset within one cell). Older snapshots may
  // retain net cells only; their gross stays explicitly unavailable.
  vexGross = null;
  if(vexHit && Array.isArray(displayGrid?.vex_strike_gross)) {
    const grossByStrike = new Map();
    const duplicate = new Set();
    for(const r of displayGrid.vex_strike_gross) {
      const strike = Number(r?.strike);
      if(grossByStrike.has(strike))duplicate.add(strike);
      grossByStrike.set(strike,r?.vex_gross);
    }
    if([...vexMembers].every(s=>!duplicate.has(s) && typeof grossByStrike.get(s)==="number"
       && Number.isFinite(grossByStrike.get(s)) && grossByStrike.get(s)>=0)) {
      vexGross=[...vexMembers].reduce((sum,s)=>sum+grossByStrike.get(s),0);
    }
  }
  const win = wallRecentWindow(wallWin, metrics);
  const winNote = win.value;
  const cell = (v) => (v == null ? "—" : fmtUsd(v));
  // Shared semantics (2026-10-17): this table and the compact FocusSummary
  // use the same wallDeltaWeighted / wallSessionVolume /
  // wallSessionDeltaVolume helpers, so the missing/zero/coverage language
  // can never drift between the two surfaces.
  const d = wallDeltaWeighted(wb);
  const dUsable = d.usable;
  const dMissing = d.missing;
  const dInvalidDelta = d.invalid;
  const dAbsentNote = d.absentNote;
  const dVal = d.value;
  const sv = wallSessionVolume(wb);
  const vN = sv.usable;
  const vMissing = sv.missing;
  const vInvalid = sv.invalid;
  const vVal = sv.value;
  const dv = wallSessionDeltaVolume(wb);
  const dvN = dv.usable;
  const dvMissing = dv.missing;
  const dvInvalid = dv.invalid;
  const dvVal = dv.value;
  const vexScope = displayGrid?.vex_meta;
  const scopeNotes = [
    ["missing_vanna_inputs", "missing inputs"],
    ["quarantined", "quarantined"], ["invalid_type", "invalid types"],
  ].filter(([key])=>usableCount(vexScope?.[key])>0)
    .map(([key,label])=>String(vexScope[key])+" "+label);
  const vexBasis = vexHit
    ? "local-bs-vanna.v1 · "+vexMembers.size+"/"+members.length+" member strikes · "+vexHit+
      " cells · USD delta-notional/+1 vol point"+(vexGross == null ? " · gross unavailable" : "")+
      (scopeNotes.length ? " · scope: "+scopeNotes.join(", ") : "")
    : "no VEX coverage at members";
  const rows = [
    ["Raw gross / net", `${cell(wall.gross)} / ${cell(wall.net)}`, "OI · gex.v2"],
    ["Δ gross / net", dVal,
      wb ? `OI Δ-weighted · ${dUsable ?? "unknown"} usable${dMissing ? ` · ${dMissing} δ-missing` : ""}${dInvalidDelta ? ` · ${dInvalidDelta} δ-invalid (unusable reading)` : ""}${wb.invalid ? ` · ${wb.invalid} invalid` : ""}` : "no wall breakdown"],
    ["VEX gross / net", vexNet == null ? "—" : `${cell(vexGross)} / ${cell(vexNet)}`,
      vexBasis],
    ["Session activity", vVal,
      wb ? `session volume · ${vN ?? "unknown"} usable contracts${vMissing ? ` · ${vMissing} volume missing` : ""}${vInvalid ? ` · ${vInvalid} invalid` : ""}${vMissing == null || vInvalid == null ? " · coverage details unavailable" : ""}` : "no wall breakdown"],
    ["Session vol × |Δ|", dvVal,
      `session volume × |delta| · ${dvN ?? "unknown"} usable${dvMissing ? ` · ${dvMissing} missing` : ""}${dvInvalid ? ` · ${dvInvalid} invalid` : ""} · not trade-signed flow`],
    ["Recent window", winNote, "window Δ-weighted · member coverage"],
  ];
  return (
    <table data-testid="wall-compare-table" className="skylit-compare-table">
      <tbody>
        {rows.map(([k, v, basis]) => (
          <tr key={k} title={basis}>
            <th scope="row"><span>{k}</span><small className="skylit-compare-basis">{basis}</small></th>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}


/**
 * InteractionTimeline — R7-05 observed wall-interaction timeline from the
 * current interaction record's temporal markers (approach → first touch →
 * current state/event → beyond). Single-record summary, not a full event
 * log; repeats of the same observation never fabricate new entries.
 */
function InteractionTimeline({ interaction }) {
  if (!interaction) return null;
  const items = [];
  if (interaction.approach_side) items.push(["approached", `from ${interaction.approach_side}`]);
  if (interaction.inside_since) items.push(["first touch", String(interaction.inside_since).slice(0, 16).replace("T", " ")]);
  items.push([interaction.state || "unobserved",
    [interaction.event, interaction.at ? String(interaction.at).slice(0, 16).replace("T", " ") : null].filter(Boolean).join(" · ") || "—"]);
  if (interaction.beyond_since) items.push(["accepted beyond", `${interaction.beyond_side || "?"} · ${String(interaction.beyond_since).slice(0, 16).replace("T", " ")}`]);
  if (!items.length) return null;
  return (
    <div data-testid="wall-timeline" className="skylit-inspector-note">
      {items.map(([k, v], i) => (
        <div key={`${k}-${i}`}>· {k}{v ? `: ${v}` : ""}</div>
      ))}
    </div>
  );
}


/**
 * Readiness — R7-05 one concise readiness state: Observe / Wait /
 * Confirmed for review / Invalidated, with the primary reason.
 * Deterministic rule, documented here: false eligibility always blocks;
 * invalidation beats everything except nothing; confirmation needs a
 * holding/rejecting/accepted state plus eligibility plus a scenario.
 * "Confirmed for review" is never an order.
 */
export function readinessOf(interaction, quality, scenario) {
  const state = interaction?.state || "unobserved";
  const eligible = quality?.setupEligible === true;
  const reasons = (quality?.reasonCodes || []).filter(Boolean);
  if (state === "invalidated" || state === "expired") {
    return ["Invalidated", interaction?.event || interaction?.adverse_side || "invalidation observed"];
  }
  if (!eligible) {
    return ["Wait", reasons[0] || "setup blocked (reason unavailable)"];
  }
  if ((state === "holding" || state === "rejecting" || state === "accepted_beyond") && scenario) {
    return ["Confirmed for review", scenario.name || state];
  }
  return ["Observe", state === "unobserved" ? "awaiting price confirmation" : `watching (${state})`];
}

function Readiness({ interaction, quality, scenario }) {
  const [label, reason] = readinessOf(interaction, quality, scenario);
  return (
    <div data-testid="wall-readiness" title="Deterministic readiness (not an order)"
      className="skylit-inspector-note">
      Readiness: <strong>{label}</strong> — {reason}
    </div>
  );
}


/**
 * ExplainThisWall — R6-4 mounted deterministic explainer. Optional detail
 * block rendered from typed snapshot fields (no model). Keyed by
 * snapshot+wall+metric+mode so a stale explanation unmounts instead of
 * lingering after selection/scope/mode changes.
 */
function ExplainThisWall({ snapshotId, wall, metric, replay,
                           interaction, scenarios, quality,
                           wallWindow, windowReason }) {
  const out = explainWall({
    snapshotId, wall, metric, mode: replay ? "replay" : "live",
    interaction, scenarios, quality, wallWindow, windowReason,
  });
  if (!out) return null;
  const key = `${out.snapshotId || "?"}:${out.wallId || "?"}:${out.metric}:${out.mode}`;
  return (
    <details key={key} data-testid="wall-explainer">
      <summary>Explain this wall (deterministic{replay ? ", replay" : ""})</summary>
      <div style={{ fontSize: 12, color: "#94a3b8" }}>
        {out.blocks.map((b) => (
          <div key={b.id} style={{ marginTop: 4 }}>
            <strong>{b.title}.</strong> {b.text}
          </div>
        ))}
      </div>
    </details>
  );
}


function ScoutSummary({ scout, members = [] }) {
  if (!scout) return null;
  const rej = scout.rejected || {};
  const top = Object.entries(rej)
    .map(([reason, pair]) => ({ reason, n: (Array.isArray(pair) ? pair[0] + pair[1] : Number(pair) || 0) }))
    .sort((a, b) => b.n - a.n)
    .slice(0, 5);
  // R7-05: bounded read-only review rows (3/side). Wall linkage is explicit:
  // each row is tagged in/out of the SELECTED wall; the shortlist is never
  // silently re-ranked to another wall (selection is UI state).
  const memberSet = new Set((members || []).map((s) => Number(s)));
  const short = scout.shortlist || {};
  const sides = ["CALLS", "PUTS"].filter((s) => Array.isArray(short[s]));
  const hasRows = sides.some((s) => short[s].length > 0);
  const age = (ts) => (ts ? String(ts).slice(11, 19) : "age unknown");
  return (
    <details>
      <summary>0DTE candidates (read-only)</summary>
      <div style={{ fontSize: 12, color: "#94a3b8" }}>
        calls eligible: {scout.calls ?? "—"} · puts eligible: {scout.puts ?? "—"}
        {top.length > 0 && (
          <> · rejected: {top.map((r) => `${r.reason} ×${r.n}`).join(", ")}</>
        )}
        <br />
        {hasRows ? sides.map((s) => (
          <div key={s} style={{ marginTop: 4 }}>
            <div data-testid={`shortlist-${s.toLowerCase()}`}>
              {s} shortlist ({short[s].filter((r) => memberSet.has(Number(r.strike))).length}/{short[s].length} in this wall):
            </div>
            <table className="skylit-shortlist-table">
              <tbody>
                {short[s].map((r) => (
                  <tr key={`${s}-${r.osi}`} data-testid="shortlist-row">
                    <td>{memberSet.has(Number(r.strike)) ? "●" : "○"}</td>
                    <td>{r.osi}</td>
                    <td>{r.expiry} · Δ {r.delta}</td>
                    <td>{r.bid}×{r.ask}{r.spread_pct != null ? ` (${r.spread_pct.toFixed(1)}%)` : ""}</td>
                    <td>q {age(r.bid_ts)}/{age(r.ask_ts)}{r.tick_unknown ? " · tick unknown" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )        ) : (
          <div data-testid="shortlist-empty">
            No eligible contracts. A withheld setup is a valid result — see
            rejection counts above for what blocked review.
          </div>
        )}
        <br />
        Eligibility is not a confirmed setup; zero candidates is valid. No order action.
      </div>
    </details>
  );
}


function ContextSections({ scout, patterns, regime, vanna, moneyness, members = [] }) {
  const pats = Array.isArray(patterns) ? patterns
    : (patterns && Array.isArray(patterns.patterns) ? patterns.patterns : null);
  const regSign = regime?.sign;
  const buckets = moneyness?.buckets;
  const bandRows = buckets && typeof buckets === "object"
    ? Object.entries(buckets)
      .map(([band, b]) => ({ band, oi: Number(b?.oi) || 0, volume: Number(b?.volume) || 0, n: Number(b?.n) || 0 }))
      .sort((a, b) => b.oi - a.oi)
      .slice(0, 6)
    : [];
  // R7-05: real vanna per-expiry values (contract-vanna units, not USD).
  const vannaRows = vanna && vanna.by_expiry && typeof vanna.by_expiry === "object"
    ? Object.entries(vanna.by_expiry)
      .map(([exp, b]) => ({ exp, vanna: Number(b?.vanna) || 0, vomma: Number(b?.vomma) || 0, n: Number(b?.n) || 0 }))
      .sort((a, b) => Math.abs(b.vanna) - Math.abs(a.vanna))
      .slice(0, 6)
    : [];
  if (!scout && !pats && regSign == null && !vannaRows.length && !bandRows.length) return null;
  return (
    <div style={{ marginTop: 6 }}>
      <ScoutSummary scout={scout} members={members} />
      {(pats || regSign != null) && (
        <details>
          <summary>Pattern + regime context</summary>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>
            {regSign != null && <>regime: {String(regSign)} (context, not direction). {regime?.reason === "MODEL_INPUTS_INCOMPLETE" && "Options data is incomplete; no reliable sign or zero-gamma level is available. "}</>}
            {pats ? <>patterns: {pats.length ? pats.map((p) => `${p.pattern_id || p.id}(${p.state || "?"})`).join(", ") : "none"}. Candidates lack temporal evidence; names are not forecasts.</> : <>patterns: unavailable.</>}
          </div>
        </details>
      )}
      {(vannaRows.length > 0 || bandRows.length > 0) && (
        <details>
          <summary>Advanced: vanna / moneyness</summary>
          <div style={{ fontSize: 12, color: "#94a3b8" }} data-testid="advanced-values">
            {vannaRows.length > 0 && (
              <>vanna/expiry (contract-vanna units = vanna·OI·100, not USD):{" "}
                {vannaRows.map((r) => `${r.exp.slice(5)} ${r.vanna >= 0 ? "+" : ""}${r.vanna.toExponential(1)} (n=${r.n})`).join(" · ")}. Research only. </>
            )}
            {bandRows.length > 0 && (
              <>moneyness (OI concentration by delta band):{" "}
                {bandRows.map((r) => `${r.band} OI ${r.oi >= 1e6 ? `${(r.oi / 1e6).toFixed(1)}M` : Math.round(r.oi)} (n=${r.n})`).join(" · ")}. Distribution only.</>
            )}
          </div>
        </details>
      )}
    </div>
  );
}

export default memo(WallInspector);
