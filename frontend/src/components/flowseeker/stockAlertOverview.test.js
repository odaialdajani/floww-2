import {spreadStockAlerts} from './stockAlertOverview';
const crowded=[...Array.from({length:14},(_,i)=>({key:'qqq-'+i,under:'QQQ',conviction:99,asof_ts:'2026-10-06T20:00:00Z'})),...Array.from({length:12},(_,i)=>({key:'spy-'+i,under:'SPY',conviction:98,asof_ts:'2026-10-06T19:00:00Z'})),...['NVDA','AMD','TSLA','AAPL','MSFT','AMZN','META','MU','CSCO','AVGO'].map(under=>({key:under,under,conviction:65,asof_ts:null}))];
test('repeated fund readings cannot hide every other stock on the first page',()=>{
 const output=spreadStockAlerts(crowded);expect(new Set(output.slice(0,8).map(x=>x.under)).size).toBe(8);expect(output.slice(0,8).some(x=>x.under==='NVDA')).toBe(true);
 expect(output).toHaveLength(crowded.length);expect(new Set(output)).toEqual(new Set(crowded));
 expect(output.find(x=>x.under==='NVDA').asof_ts).toBeNull();expect(crowded.slice(0,14).every(x=>x.under==='QQQ')).toBe(true);
});
test('a pinned stock starts once while other stocks keep their first place',()=>{
 const pinned=crowded[0];const body=crowded.slice(1);const output=spreadStockAlerts(body,pinned.under);expect(output.slice(0,7).every(x=>x.under!=='QQQ')).toBe(true);expect(output).toHaveLength(body.length);expect(new Set(output)).toEqual(new Set(body));
});
test('unknown stock names are not discarded or merged into one reading',()=>{
 const rows=[{key:'unknown-1',under:null},{key:'unknown-2',under:null},{key:'a',under:'AAPL'},{key:'b',ticker:'aapl'}];const output=spreadStockAlerts(rows);expect(output).toHaveLength(4);expect(new Set(output)).toEqual(new Set(rows));
});
