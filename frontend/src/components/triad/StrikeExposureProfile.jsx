import React, { useMemo } from "react";
import { ProfileBars } from "../heatseeker/SkylitHeatmapGrid";
import { shownMapStrikes } from "../heatseeker/shownMapStrikes";
import { sumProfile, baseDef, fmtUsdCompact } from "../../lib/solsticeMetrics";

export default function StrikeExposureProfile({ data, basis, wall, onSelect }) {
  const expiries = data?.grid?.expiries || [];
  const raw = useMemo(() => sumProfile(data, "raw", expiries), [data, expiries]);
  const adj = useMemo(() => sumProfile(data, basis, expiries), [data, basis, expiries]);
  const max = Math.max(raw.maxAbs, adj.maxAbs);
  const strikes = shownMapStrikes(data, data?.spot, null);
  return <section className="triad-profile" data-testid="triad-signed-profile" aria-label="Signed exposure by strike">
    <div>Signed exposure by strike · All loaded · {expiries.length} expiries · USD/1% move</div>
    <small>Raw under · {baseDef(basis)?.label || basis} over · shared range · zero axis centered · gaps ≠ zero</small>
    <table><tbody>{strikes.map(s => {
      const key = String(s), r = raw.values[key] ?? null, a = adj.values[key] ?? null;
      const selected = wall && s >= wall.low && s <= wall.high;
      return <tr key={key} className={selected ? "selected" : ""}>
        <td><button onClick={() => onSelect(s)} aria-label={`Select raw wall at strike ${s}`}>{s}</button></td>
        <td><ProfileBars raw={r} adj={a} rawMax={max} adjMax={max} adjLabel={baseDef(basis)?.label || basis} partial={adj.partial[key] || 0} invalid={adj.invalid[key] || 0} /></td>
        <td title={`Raw ${fmtUsdCompact(r)}; ${basis} ${fmtUsdCompact(a)}`}>{fmtUsdCompact(r)}</td>
      </tr>;
    })}</tbody></table>
  </section>;
}
