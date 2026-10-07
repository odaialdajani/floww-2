import {mapPublicChainToRows} from './FlowseekerProBlademap';
jest.mock('./MarketCoverage',()=>()=>null);
const contract=more=>({strike:450,type:'call',expiry:'2026-11-06',volume:5000,oi:1000,iv:.2,bid:4,ask:4.2,last:4.1,...more});
test.each([null,undefined,false,-1,.9])('missing or invalid open interest never becomes a made-up ratio: %s',oi=>{const rows=mapPublicChainToRows([contract({oi})],450,'SPY');expect(rows).toHaveLength(1);expect(rows[0].oi).toBeNull();expect(rows[0].vol_oi_ratio).toBeNull();});
test('genuine zero open interest stays zero while its ratio is unavailable',()=>{const [row]=mapPublicChainToRows([contract({oi:0})],450,'SPY');expect(row.oi).toBe(0);expect(row.vol_oi_ratio).toBeNull();});
test('a quote-free price estimate is clearly separate from quoted money',()=>{const [row]=mapPublicChainToRows([contract({last:0,bid:0,ask:0})],450,'SPY');expect(row.priceBasis).toBe('model_estimate');expect(row.quotePrice).toBeNull();expect(row.premium).toBeGreaterThan(0);});
test('one-sided quote never silently supplies a zero second side',()=>{const [row]=mapPublicChainToRows([contract({last:null,bid:null,ask:4.2})],450,'SPY');expect(row.priceBasis).toBe('model_estimate');expect(row.quotePrice).toBeNull();});
test('missing volatility and strike do not create fake zeros',()=>{const [row]=mapPublicChainToRows([contract({strike:null,iv:null,last:0,bid:0,ask:0})],450,'SPY');expect(row.strike).toBeNull();expect(row.iv).toBeNull();expect(row.premium).toBeNull();});
test('fractional or invalid contract volume is not a counted reading',()=>{expect(mapPublicChainToRows([contract({volume:2500.8}),contract({volume:true}),contract({volume:Infinity})],450,'SPY')).toEqual([]);});

test('malformed count lists never become scalar counts',()=>{expect(mapPublicChainToRows([contract({volume:[5000]})],450,'SPY')).toEqual([]);const [row]=mapPublicChainToRows([contract({oi:[1000]})],450,'SPY');expect(row.oi).toBeNull();expect(row.vol_oi_ratio).toBeNull();});
test('a malformed price list is not a quoted price',()=>{const [row]=mapPublicChainToRows([contract({last:[4.1],bid:null,ask:null})],450,'SPY');expect(row.quotePrice).toBeNull();expect(row.priceBasis).toBe('model_estimate');});
