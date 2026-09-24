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
  const wallWin = (metrics?.wall_window || {})[wall.wall_id || ""];
  const winReason = metrics?.window_daddex_reason;
  const winNote = wallWin
    ? `${fmtUsd(wallWin.window_daddex)} (window Δ-weighted · ${wallWin.coverage.active_strikes}/${wallWin.coverage.member_strikes} strikes)`
    : winReason === "VOLUME_REBASE" ? "unavailable — volume rebase, new baseline required"
    : "unavailable — no comparable window for this wall";
  // R6-2 same-wall comparison: raw (wall record), delta-weighted and session
  // activity (wall_metrics breakdown). Each declares its basis; unlike
  // quantities are never blended and scope totals stay out of this table.
  const wb = (metrics?.wall_metrics || {})[wall.wall_id || ""];
  const compareNote = wb
    ? `raw ${fmtUsd(wall.gross)}/${fmtUsd(wall.net)} (OI) · Δ ${fmtUsd(wb.daddex_gross)}/${fmtUsd(wb.daddex_net)} (OI Δ-weighted${wb.daddex_missing ? `, ${wb.daddex_missing} δ-missing` : ""}) · session ${fmtUsd(wb.volume_net)} (volume)`
    : null;
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
      {compareNote && (
        <Row k="Same-wall compare" v={compareNote} tip="Same wall, same scope: raw OI structure vs delta-weighted structure vs session volume activity. Unlike quantities, separately labeled." />
      )}
      <Row k="Window activity" v={winNote} tip="This wall's member strikes only, with member/active-strike coverage; turnover, never buyer-minus-seller flow" />
      <Row k="Δ provenance" v={pairNote} tip="Vendor/vendor, local/local eligible; mixed pairs blocked without policy" />
      <Row k="OI eff. date" v={(wall.oi_effective_dates && wall.oi_effective_dates.length ? wall.oi_effective_dates.join(", ") : null) ?? "unavailable in snapshot"} tip="Per-wall OI effective dates from member-strike provenance; unavailable when no member carries OI metadata" />
      <Row k="Changed" v={interaction ? `${interaction.state}${interaction.event ? ` · ${interaction.event}` : ""}${interaction.first_seen === false ? " · persistent" : " (first sighting — see replay compare)"}` : "see replay compare"} tip="Wall-level change needs 2+ recorded snapshots; persistent states carry continuity, first sightings do not" />
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
      <ContextSections scout={scout} patterns={patterns} regime={regime} vanna={vanna} moneyness={moneyness} />
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


function ScoutSummary({ scout }) {  if (!scout) return null;
  const rej = scout.rejected || {};
  const top = Object.entries(rej)
    .map(([reason, pair]) => ({ reason, n: (Array.isArray(pair) ? pair[0] + pair[1] : Number(pair) || 0) }))
    .sort((a, b) => b.n - a.n)
    .slice(0, 5);
  return (
    <details>
      <summary>0DTE candidates (read-only)</summary>
      <div style={{ fontSize: 12, color: "#94a3b8" }}>
        calls eligible: {scout.calls ?? "—"} · puts eligible: {scout.puts ?? "—"}
        {top.length > 0 && (
          <> · rejected: {top.map((r) => `${r.reason} ×${r.n}`).join(", ")}</>
        )}
        <br />
        Eligibility is not a confirmed setup; zero candidates is valid. No order action.
      </div>
    </details>
  );
}


function ContextSections({ scout, patterns, regime, vanna, moneyness }) {
  const pats = Array.isArray(patterns) ? patterns
    : (patterns && Array.isArray(patterns.patterns) ? patterns.patterns : null);
  const regSign = regime?.sign;
  const buckets = moneyness?.buckets;
  const nBands = buckets && typeof buckets === "object" ? Object.keys(buckets).length : 0;
  if (!scout && !pats && regSign == null && !vanna && !nBands) return null;
  return (
    <div style={{ marginTop: 6 }}>
      <ScoutSummary scout={scout} />
      {(pats || regSign != null) && (
        <details>
          <summary>Pattern + regime context</summary>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>
            {regSign != null && <>regime: {String(regSign)} (context, not direction). </>}
            {pats ? <>patterns: {pats.length ? pats.map((p) => `${p.pattern_id || p.id}(${p.state || "?"})`).join(", ") : "none"}. Candidates lack temporal evidence; names are not forecasts.</> : <>patterns: unavailable.</>}
          </div>
        </details>
      )}
      {(vanna || nBands > 0) && (
        <details>
          <summary>Advanced: vanna / moneyness</summary>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>
            {nBands > 0 && <>moneyness bands: {nBands} (distribution only). </>}
            {vanna && <>vanna view present (units/scope/provenance per payload; research only).</>}
          </div>
        </details>
      )}
    </div>
  );
}

export default memo(WallInspector);
