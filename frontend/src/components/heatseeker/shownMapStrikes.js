// Shared by the rendered table and frozen research selection.
export function mapSurface(data, viewMode = "gex", metric = "raw") {
 const key = {gex:"grid",skylit:"grid",vex:"vex_grid",charm:"charm_grid"}[viewMode];
 const useOverlay = metric !== "raw" && ["gex","skylit"].includes(viewMode);
 const section = useOverlay ? data?.metrics?.grids?.[metric] : data?.grid;
 const available = !!section && !!key && !!section[key];
 return {
  matrix: available ? section[key] : {},
  strikes: section?.strikes?.length ? section.strikes : (data?.grid?.strikes?.length ? data.grid.strikes : (data?.strikes || []).map(s=>s.strike)),
  expiries: section?.expiries?.length ? section.expiries : (data?.grid?.expiries || []),
  available,
 };
}

export function shownMapStrikes(data, spot, windowRows = null, viewMode = "gex", metric = "raw") {
 const src = mapSurface(data,viewMode,metric).strikes;
 const strikes = [...new Set(src)].filter(s=>s!=null).sort((a,b)=>b-a);
 if(windowRows == null || strikes.length <= windowRows) return strikes;
 let center = Math.floor(strikes.length / 2);
 if(spot != null && strikes.length) {
  center = 0;
  for(let i=1;i<strikes.length;i++) if(Math.abs(strikes[i]-spot)<Math.abs(strikes[center]-spot)) center=i;
 }
 const start=Math.max(0,Math.min(center-Math.floor(windowRows/2),strikes.length-windowRows));
 return strikes.slice(start,start+windowRows);
}
