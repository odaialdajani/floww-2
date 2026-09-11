// Shared by the rendered table and frozen research selection.
export function shownMapStrikes(data, spot, windowRows = null) {
 const src = data?.grid?.strikes?.length ? data.grid.strikes : (data?.strikes || []).map(s=>s.strike);
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
