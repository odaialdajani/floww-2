import React, { useLayoutEffect, useMemo, useRef } from "react";
import { ProfileBars } from "../heatseeker/SkylitHeatmapGrid";
import { shownMapStrikes } from "../heatseeker/shownMapStrikes";
import { sumProfile, baseDef, fmtUsdCompact } from "../../lib/solsticeMetrics";

export default function StrikeExposureProfile({ data, basis, wall, onSelect }) {
  const expiries = data?.grid?.expiries || [];
  const raw = useMemo(() => sumProfile(data, "raw", expiries), [data, expiries]);
  const adj = useMemo(() => sumProfile(data, basis, expiries), [data, basis, expiries]);
  const max = Math.max(raw.maxAbs, adj.maxAbs);
  const strikes = shownMapStrikes(data, data?.spot, null);
  const listRef = useRef(null);
  const spotValid = typeof data?.spot === "number" && Number.isFinite(data.spot) && data.spot > 0;
  useLayoutEffect(() => {
    if (!spotValid || data?.replay) return;
    const list = listRef.current;
    if (!list || list.dataset.centered === "1") return;
    list.dataset.centered = "1";
    centerOnPrice();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spotValid, data?.replay, strikes.join(",")]);
  const centerOnPrice = () => {
    const list = listRef.current;
    const spot = Number(data?.spot);
    if (!list || !(typeof spot === "number" && Number.isFinite(spot) && spot > 0)) return;
    let best = null, bestDist = Infinity;
    for (const row of [...list.querySelectorAll("tr")]) {
      const strike = Number(row.dataset.strike);
      if (!Number.isFinite(strike)) continue;
      const dist = Math.abs(strike - spot);
      if (dist < bestDist) { bestDist = dist; best = row; }
    }
    if (!best) return;
    const bounds = list.getBoundingClientRect(), target = best.getBoundingClientRect();
    list.scrollTop += target.top - bounds.top - (list.clientHeight - target.height) / 2;
  };
  return <section className="triad-profile" data-testid="triad-signed-profile" aria-label="Signed exposure by strike">
    <div>Signed exposure by strike · All loaded · {expiries.length} expiries · USD/1% move <button type="button" onClick={centerOnPrice} disabled={!(typeof data?.spot === "number" && Number.isFinite(data.spot) && data.spot > 0)} title={typeof data?.spot === "number" && data.spot > 0 ? `Center the profile on the price region (${data.spot})` : "Price unavailable"}>Center exposure profile on price</button></div>
    <small>Raw under · {baseDef(basis)?.label || basis} over · shared range · zero axis centered · gaps ≠ zero</small>
    <table><tbody ref={listRef}>{strikes.map(s => {
      const key = String(s), r = raw.values[key] ?? null, a = adj.values[key] ?? null;
      const selected = wall && s >= wall.low && s <= wall.high;
      return <tr key={key} data-strike={s} className={selected ? "selected" : ""}>
        <td><button onClick={() => onSelect(s)} aria-label={`Select raw wall at strike ${s}`}>{s}</button></td>
        <td><ProfileBars raw={r} adj={a} rawMax={max} adjMax={max} adjLabel={baseDef(basis)?.label || basis} partial={adj.partial[key] || 0} invalid={adj.invalid[key] || 0} /></td>
        <td title={`Raw ${fmtUsdCompact(r)}; ${basis} ${fmtUsdCompact(a)}`}>{fmtUsdCompact(r)}</td>
      </tr>;
    })}</tbody></table>
  </section>;
}
