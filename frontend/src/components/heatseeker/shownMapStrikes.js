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

// Window of `windowRows` descending strikes centered on `anchor` when given
// (follow-spot paused), else on spot. The anchor never changes the
// calculation universe — only which rows are on screen.
export function shownMapStrikes(data, spot, windowRows = null, viewMode = "gex", metric = "raw", anchor = null) {
 const src = mapSurface(data,viewMode,metric).strikes;
 const strikes = [...new Set(src)].filter(s=>s!=null).sort((a,b)=>b-a);
 if(windowRows == null || strikes.length <= windowRows) return strikes;
 const target = anchor != null && Number.isFinite(Number(anchor)) ? Number(anchor) : spot;
 let center = Math.floor(strikes.length / 2);
 if(target != null && strikes.length) {
  center = 0;
  for(let i=1;i<strikes.length;i++) if(Math.abs(strikes[i]-target)<Math.abs(strikes[center]-target)) center=i;
 }
 const start=Math.max(0,Math.min(center-Math.floor(windowRows/2),strikes.length-windowRows));
 return strikes.slice(start,start+windowRows);
}

// Shift a window anchor by `rows` strikes (positive = toward lower strikes).
export function stepAnchor(data, currentCenter, rows, viewMode = "gex", metric = "raw") {
 const strikes = [...new Set(mapSurface(data,viewMode,metric).strikes)].filter(s=>s!=null).sort((a,b)=>b-a);
 if(!strikes.length) return null;
 let i = 0;
 if(currentCenter != null) {
  for(let j=1;j<strikes.length;j++) if(Math.abs(strikes[j]-currentCenter)<Math.abs(strikes[i]-currentCenter)) i=j;
 }
 const next = Math.max(0, Math.min(strikes.length - 1, i + rows));
 return strikes[next];
}
