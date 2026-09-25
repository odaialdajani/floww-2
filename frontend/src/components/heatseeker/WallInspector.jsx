import React, { memo } from "react";
import { explainWall } from "../../lib/solsticeExplain";

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
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(1)}K`;
  return `${sign}$${a.toFixed(0)}`;
}

function WallInspector({ wall = null, interaction = null, metrics = null, grids = null, quality = null, scenario = null, goneReason = null, lastWallId = null,
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
  const members = wall.members || [];
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
          if (col[k] != null) { sum += col[k]; hit = true; }
        }
        if (hit && !seen.has(`${name}|${exp}`)) {
          seen.add(`${name}|${exp}`);
          perExpiry.push({ grid: name, expiry: exp, value: sum });
        }
      }
    }
  }
  const ratio = metrics?.magnitude_ratio_delta_over_raw;
  const pairNote = metrics
    ? `Δ usable ${metrics.dadgex_usable ?? "—"}, missing ${metrics.dadgex_missing_delta ?? "—"}`
    : "—";
  // R6-2 wall-local window activity: aggregate over THIS wall's member
  // strikes only (with member/active coverage). The whole-scope sum is never
  // shown as wall-local; without a comparable baseline the row reports why.
  // (Rendered inside CompareTable below; no separate row — one window value.)
  const wallWin = (metrics?.wall_window || {})[wall.wall_id || ""];
  const winReason = metrics?.window_daddex_reason;
  // R6-2 same-wall comparison: raw (wall record), delta-weighted and session
  // activity (wall_metrics breakdown). Each declares its basis; unlike
  // quantities are never blended and scope totals stay out of this table.
  const wb = (metrics?.wall_metrics || {})[wall.wall_id || ""];
  return (
    <div className="skylit-metrics-section" data-testid="wall-inspector">
      <div className="skylit-section-title">Selected wall · {wall.wall_id || `${wall.low}–${wall.high}`}</div>
      <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 6 }}>Now / Changed / Confirm / Invalidates</div>
      <Row k="Now" v={`${wall.low}–${wall.high} · gross ${fmtUsd(wall.gross)} · net ${fmtUsd(wall.net)} (USD/1% move, ${wall.exposure_basis || "OI"})`} />
      <Row k="Call / Put" v={`${fmtUsd(wall.call)} / ${fmtUsd(wall.put)}`} tip="Call-plus vs put-minus components; high gross + near-zero net is two-sided concentration" />
      <Row k="Distance" v={wall.distance != null ? `${Number(wall.distance).toFixed(2)} (${(Number(wall.distance_pct) * 100).toFixed(2)}%)` : "—"} />
      {perExpiry.length > 0 && (
        <Row k="Per-expiry" v={perExpiry.slice(0, 6).map((p) => `${p.grid}:${p.expiry.slice(5)}=${fmtUsd(p.value)}`).join(" · ")} tip="Same-snapshot per-expiry contributions for member strikes" />
      )}
      <Row k="Δ/Raw (scope)" v={ratio != null ? Number(ratio).toFixed(3) : "—"} tip="Scope-wide delta gross / raw gross over the same snapshot set — not the selected wall. Wall-local ratio needs same-wall delta + raw grids." />
      <CompareTable wall={wall} metrics={metrics} grids={grids} />
      <Row k="Δ provenance" v={pairNote} tip="Vendor/vendor, local/local eligible; mixed pairs blocked without policy" />
      <Row k="OI eff. date" v={(wall.oi_effective_dates && wall.oi_effective_dates.length ? wall.oi_effective_dates.join(", ") : null) ?? "unavailable in snapshot"} tip="Per-wall OI effective dates from member-strike provenance; unavailable when no member carries OI metadata" />
      <Row k="Changed" v={interaction ? `${interaction.state}${interaction.event ? ` · ${interaction.event}` : ""}${interaction.first_seen === false ? " · persistent" : " (first sighting — see replay compare)"}` : "see replay compare"} tip="Wall-level change needs 2+ recorded snapshots; persistent states carry continuity, first sightings do not" />
      <InteractionTimeline interaction={interaction} />
      <Readiness interaction={interaction} quality={quality} scenario={scenario} />
      <Row k="Interaction" v={interaction ? interaction.state : "unobserved"} tip="Time-debounced state machine; session/feed gaps break continuity" />
      <Row k="Touches" v={interaction && interaction.taps != null ? String(interaction.taps) : "unknown — no history"} tip="Observed touches only; never a calibrated probability" />
      <Row k="Confirm" v={scenario?.confirmation || "reclaim and hold above zone"} />
      <Row k="Invalidates" v={scenario?.invalidation || "acceptance beyond zone"} />
      <Row k="Data" v={quality ? `${quality.state || "unknown"} · ${(quality.reasonCodes || []).join(", ") || "ok"}` : "unknown"} />
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
 * CompareTable — R7-05 small same-wall comparison table (replaces the long
 * compressed string): raw gross/net, delta gross/net, VEX gross/net,
 * session activity and recent-window activity. Same member contracts and
 * snapshot; each row declares basis/coverage; missing is "—", never zero.
 */
function CompareTable({ wall, metrics, grids }) {
  const members = wall.members || [];
  const wb = (metrics?.wall_metrics || {})[wall.wall_id || ""];
  const wallWin = (metrics?.wall_window || {})[wall.wall_id || ""];
  // Wall-local VEX from the canonical surface (same members, same snapshot).
  let vexNet = null;
  let vexGross = null;
  let vexHit = 0;
  const vexSection = grids && grids.grid ? grids.grid.vex_grid : null;
  if (vexSection && members.length) {
    vexNet = 0;
    vexGross = 0;
    for (const col of Object.values(vexSection)) {
      for (const s of members) {
        const k = Number.isInteger(s) ? String(s) : String(s);
        const v = col ? col[k] : null;
        if (typeof v === "number" && Number.isFinite(v)) {
          vexNet += v;
          vexGross += Math.abs(v);
          vexHit += 1;
        }
      }
    }
    if (!vexHit) {
      vexNet = null;
      vexGross = null;
    }
  }
  const winCov = (wallWin && wallWin.coverage) || {};
  const winNote = wallWin
    ? `${fmtUsd(wallWin.window_daddex)} · ${winCov.active_strikes ?? "—"}/${winCov.member_strikes ?? "—"} strikes`
    : ((metrics?.window_daddex_reason === "VOLUME_REBASE")
      ? "unavailable — volume rebase"
      : "unavailable — no comparable window");
  const cell = (v) => (v == null ? "—" : fmtUsd(v));
  const rows = [
    ["Raw gross / net", `${cell(wall.gross)} / ${cell(wall.net)}`, "OI · gex.v2"],
    ["Δ gross / net", wb ? `${cell(wb.daddex_gross)} / ${cell(wb.daddex_net)}` : "—",
      wb ? `OI Δ-weighted${wb.daddex_missing ? ` · ${wb.daddex_missing} δ-missing` : ""}` : "no wall breakdown"],
    ["VEX gross / net", vexGross == null ? "—" : `${cell(vexGross)} / ${cell(vexNet)}`,
      vexGross == null ? "no VEX coverage at members" : `local-bs-vanna.v1 · ${vexHit} cells`],
    ["Session activity", wb ? `${cell(wb.volume_gross)} / ${cell(wb.volume_net)}` : "—",
      wb ? `session volume · ${wb.volume_n ?? "—"} contracts` : "no wall breakdown"],
    ["Recent window", winNote, "window Δ-weighted · member coverage"],
  ];
  return (
    <table data-testid="wall-compare-table" style={{ fontSize: 12, color: "#94a3b8", marginTop: 4, borderCollapse: "collapse" }}>
      <tbody>
        {rows.map(([k, v, basis]) => (
          <tr key={k}>
            <td style={{ paddingRight: 8, whiteSpace: "nowrap" }}>{k}</td>
            <td style={{ paddingRight: 8 }}>{v}</td>
            <td style={{ opacity: 0.75 }}>{basis}</td>
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
    <div data-testid="wall-timeline" style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>
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
      style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>
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
            <table style={{ borderCollapse: "collapse" }}>
              <tbody>
                {short[s].map((r) => (
                  <tr key={`${s}-${r.osi}`} data-testid="shortlist-row">
                    <td style={{ paddingRight: 6 }}>{memberSet.has(Number(r.strike)) ? "●" : "○"}</td>
                    <td style={{ paddingRight: 6 }}>{r.osi}</td>
                    <td style={{ paddingRight: 6 }}>{r.expiry} · Δ {r.delta}</td>
                    <td style={{ paddingRight: 6 }}>{r.bid}×{r.ask}{r.spread_pct != null ? ` (${r.spread_pct.toFixed(1)}%)` : ""}</td>
                    <td style={{ opacity: 0.75 }}>q {age(r.bid_ts)}/{age(r.ask_ts)}{r.tick_unknown ? " · tick unknown" : ""}</td>
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
            {regSign != null && <>regime: {String(regSign)} (context, not direction). </>}
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
