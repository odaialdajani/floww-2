import {checkedCandles,savedLevels,clampWindow,zoomTime,zoomPrice,pinchFactors,priceRange} from './recordedPriceChartData';
const bar=(time='2026-10-06T14:00:00Z',changes={})=>({time,open:100,high:102,low:99,close:101,...changes});
test('bad prices, impossible candles, ambiguous times and duplicate instants do not become chart data',()=>{
 const valid=bar(),input=[valid,bar('2026-10-06T14:00:00+00:00'),bar('2026-10-06T14:30:00Z',{high:98}),bar('2026-10-06T15:00:00Z',{open:0}),bar('2026-10-06T14:00:00'),null];
 expect(checkedCandles(input)).toEqual([valid]);expect(input).toHaveLength(6);
});
test('candles remain ordered without inserting prices into overnight gaps',()=>{
 const before=bar('2026-10-05T20:00:00Z'),after=bar('2026-10-06T13:30:00Z');expect(checkedCandles([after,before])).toEqual([before,after]);
});
test('nodes must already have been known and still be fresh for their own candle',()=>{
 const valid=bar(undefined,{nodes_known_at:'2026-10-06T13:59:00Z',node_age_seconds:60,nodes:[{level:100},{level:104,metric:'vex'}]});
 expect(savedLevels(valid)).toHaveLength(2);expect(savedLevels({...valid,nodes_known_at:'2026-10-06T14:00:01Z'})).toEqual([]);
 expect(savedLevels({...valid,node_age_seconds:901})).toEqual([]);expect(savedLevels({...valid,node_age_seconds:null})).toEqual([]);
 expect(savedLevels({...valid,nodes_known_at:null})).toEqual([]);expect(savedLevels({...valid,node_age_seconds:-1})).toEqual([]);
});
test('nearby levels keep each metric separate, with at most two on either side of price',()=>{
 const nodes=[95,96,97,98,102,103,104].map(level=>({level}));nodes.push({level:100,metric:'vex'});
 const valid=bar(undefined,{nodes,nodes_known_at:'2026-10-06T13:59:00Z',node_age_seconds:60});
 expect(savedLevels(valid,['gex']).map(n=>n.level)).toEqual([98,97,102,103]);expect(savedLevels(valid,['vex']).map(n=>n.level)).toEqual([100]);
});
test('horizontal zoom keeps the pointed candle near the same place and stays in loaded history',()=>{
 expect(zoomTime({start:20,count:40},0.5,0.5,100)).toEqual({start:30,count:20});
 expect(zoomTime({start:60,count:40},2,1,100)).toEqual({start:20,count:80});
 expect(clampWindow({start:-9,count:20},100)).toEqual({start:0,count:20});expect(clampWindow({start:90,count:20},100)).toEqual({start:80,count:20});
});
test('vertical zoom anchors the pointed price independently from horizontal history',()=>{
 expect(zoomPrice({low:90,high:110},0.5,0.5)).toEqual({low:95,high:105});expect(zoomPrice({low:90,high:110},0.5,1)).toEqual({low:100,high:110});
});
test('horizontal and vertical two-finger spreading change only their matching scales',()=>{
 const before=[{x:20,y:20},{x:120,y:120}];expect(pinchFactors(before,[{x:20,y:20},{x:220,y:120}])).toEqual({x:0.5,y:1});
 expect(pinchFactors(before,[{x:20,y:20},{x:120,y:220}])).toEqual({x:1,y:0.5});expect(pinchFactors(before,[{x:20,y:20},{x:220,y:220}])).toEqual({x:0.5,y:0.5});
});
test('auto-fit includes real visible prices and selected saved levels, without treating missing data as zero',()=>{
 const range=priceRange([bar()],[{level:105},{level:NaN}]);expect(range.low).toBeLessThan(99);expect(range.high).toBeGreaterThan(105);expect(range.low).toBeGreaterThan(98);
});


test("explicitly unknown per-line time or age never borrows the frame clock",()=>{
 const frame=bar(undefined,{nodes_known_at:"2026-10-06T13:59:00Z",node_age_seconds:60,nodes:[{level:100,metric:"vex",known_at:null,age_seconds:1},{level:104,metric:"charm",known_at:"2026-10-06T13:59:00Z",age_seconds:null}]});expect(savedLevels(frame)).toEqual([]);
});
