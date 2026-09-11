export const finite = value => value !== null && value !== undefined && value !== "" && typeof value !== "boolean" && Number.isFinite(Number(value)) ? Number(value) : null;
export function dealerSeries(heat, flip, maxStrikes = 14) {
 const g = heat?.grid || {};
 const expiries = [...new Set(g.expiries || [])].slice(0, 6);
 let strikes = [...new Set((g.strikes || []).map(finite).filter(v => v != null))].sort((a,b) => a-b);
 const spot = finite(heat?.spot);
 if (strikes.length > maxStrikes) {
  const anchor = spot ?? strikes[Math.floor(strikes.length/2)];
  strikes = strikes.sort((a,b) => Math.abs(a-anchor)-Math.abs(b-anchor)).slice(0,maxStrikes).sort((a,b) => a-b);
 }
 const valueAt = (strike, expiry) => finite(g.grid?.[expiry]?.[String(strike)]);
 const net = strikes.map(strike => {
  const cells = expiries.map(expiry => valueAt(strike,expiry));
  return !cells.length || cells.some(v => v == null) ? null : cells.reduce((a,b)=>a+b,0);
 });
 let sum = 0;
 const cumulative = net.map(value => sum = sum == null || value == null ? null : sum + value);
 const lo = strikes[0], hi = strikes[strikes.length-1];
 const xFraction = strike => hi === lo ? 0.5 : (strike-lo)/(hi-lo);
 const flipValue = finite(flip);
 const flipFraction = flipValue != null && flipValue >= lo && flipValue <= hi ? xFraction(flipValue) : null;
 const maxMagnitude = Math.max(0,...net.filter(v=>v!=null).map(Math.abs));
 return { strikes, expiries, net, cumulative, total: cumulative.length ? cumulative[cumulative.length-1] : null,
  valueAt, maxMagnitude, xFraction, flipFraction, flip: flipValue, spot,
  complete: net.length > 0 && net.every(v=>v!=null),
  hasData: net.some(v=>v!=null) };
}
