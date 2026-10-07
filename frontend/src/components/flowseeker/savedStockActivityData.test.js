import {readSavedActivity,filterSavedActivity,savedActivityQuery,savedClock} from './savedStockActivityData';
import {BUILTIN_SCREENS} from './tideFeed';

const now=Date.parse('2026-10-07T14:00:00Z');
const row=(ticker='SPY',i=0,oi=100)=>[ticker,ticker+'-contract-'+i,'call',100+i,'2026-10-16',500,oi,.3,.5,100];
const key=r=>[r[0],r[2],r[3],r[4]].join('|');
const payload=rows=>({columns:['underlying_ticker','ticker','contract_type','strike_price','expiration_date','day_volume','open_interest','implied_volatility','delta','underlying_price'],rows,count:rows.length,total:rows.length,offset:0,limit:100,next_offset:null,status:'partial',quote_truth:{},row_observations:{},observations_by_ticker:{},coverage:{observed_tickers:new Set(rows.map(r=>Array.isArray(r)?r[0]:null)).size,missing_tickers:3}});

test('stock-balanced rows keep every ETF contract and expose other stocks on the first page',()=>{
 const rows=[...Array.from({length:40},(_,i)=>row('SPY',i)),...Array.from({length:20},(_,i)=>row('QQQ',i)),row('AAPL'),row('NVDA'),row('AMD')];
 const source=payload(rows),before=JSON.stringify(source);
 const result=readSavedActivity(source,{now});
 expect(result.rows).toHaveLength(63);
 expect(new Set(result.rows.slice(0,12).map(r=>r.under))).toEqual(new Set(['SPY','QQQ','AAPL','NVDA','AMD']));
 expect(result.rows.filter(r=>r.under==='SPY')).toHaveLength(40);
 expect(JSON.stringify(source)).toBe(before);
});

test('missing, invalid and future clocks stay unknown without using the read time',()=>{
 const source=payload([row()]);
 source.row_observations[key(source.rows[0])]={received_at:(now+1000)/1000,volume_source_time:'bad',quote_source_time:null,data_status:'legacy_limited'};
 const result=readSavedActivity(source,{now}).rows[0];
 expect(result.receiptClock.state).toBe('unknown');
 expect(result.receiptClock.reason).toBe('future');
 expect(result.volumeClock.state).toBe('unknown');
 expect(result.quoteClock.state).toBe('unknown');
 expect(result.tradeEligible).toBe(false);
 expect(result.iv).toBeNull();
 expect(result.premium).toBeNull();
 expect(result.score).toBeNull();
});

test('zero or missing open interest never creates an invented volume ratio or premium',()=>{
 const source=payload([row('SPY',0,0),row('SPY',1,null)]);
 const rows=readSavedActivity(source,{now}).rows;
 expect(rows[0].oi).toBe(0);expect(rows[0].volOI).toBeNull();expect(rows[1].volOI).toBeNull();
 expect(rows.every(r=>r.premium===null && r.score===null)).toBe(true);
 expect(filterSavedActivity(rows,{screen:BUILTIN_SCREENS.find(s=>s.id==='fresh'),now}).rows).toHaveLength(0);
});

test('only the original finite quote estimate is displayed; no premium is rebuilt',()=>{
 const source=payload([row('SPY',0),row('SPY',1)]);
 source.quote_truth[key(source.rows[0])]={premium_true:12000,premium_basis:'snapshot_volume_x_quote'};
 source.quote_truth[key(source.rows[1])]={premium_true:'not a number',mid:5};
 const rows=readSavedActivity(source,{now}).rows;
 expect(rows[0].premium).toBe(12000);expect(rows[0].premiumLabel).toBe('Quote estimate');
 expect(rows[1].premium).toBeNull();
});

test('bad rows are disclosed instead of appearing as a proven empty observation',()=>{
 const source=payload([row(),null,['BAD'],{ticker:'NVDA'}]);
 source.count=source.rows.length;
 const result=readSavedActivity(source,{now});
 expect(result.rows).toHaveLength(1);expect(result.discarded).toBe(3);expect(result.partial).toBe(true);
 expect(result.warnings.join(' ')).toMatch(/unreadable/i);
});

test('expiry today matches the exact day and never converts an expired option to today',()=>{
 const source=payload([row('SPY',0),row('QQQ',0),row('NVDA',0)]);
 source.rows[0][4]='2026-10-06';source.rows[1][4]='2026-10-07';source.rows[2][4]='2026-10-08';
 const rows=readSavedActivity(source,{now}).rows;
 expect(rows.find(r=>r.under==='SPY').dte).toBe(-1);
 const result=filterSavedActivity(rows,{screen:BUILTIN_SCREENS.find(s=>s.id==='zerodte'),now});
 expect(result.rows.map(r=>r.under)).toEqual(['QQQ']);
});

test('unsupported saved-score and custom missing-fact filters exclude unknown values explicitly',()=>{
 const rows=readSavedActivity(payload([row()]),{now}).rows;
 const scored=filterSavedActivity(rows,{filters:{minScore:1},now});
 expect(scored.rows).toHaveLength(0);expect(scored.warnings.join(' ')).toMatch(/score/i);
 const custom={custom:true,rule:'ANY',conditions:[{fact:'sigma',op:'≤',value:'10'}]};
 const result=filterSavedActivity(rows,{screen:custom,tickerFacts:{SPY:{sigma:0}},now});
 expect(result.rows).toHaveLength(0);expect(result.warnings.join(' ')).toMatch(/not recorded|unavailable/i);
});

test('queries send only supported dated-read filters, never live refresh or score settings',()=>{
 const query=new URLSearchParams(savedActivityQuery({q:' nvda ',type:'put',minVolume:1000,minScore:85,dteMin:0,dteMax:5},100));
 expect(Object.fromEntries(query)).toEqual({offset:'100',limit:'100',order:'stocks',ticker:'NVDA',contract_type:'put',min_volume:'1000'});
});


test('an impossible calendar date is unknown rather than silently shifted to another day',()=>{
 expect(savedClock('2026-02-30T14:00:00Z',now)).toMatchObject({state:'unknown',reason:'invalid',ms:null});
});

test('changed column order is unavailable instead of relabeling an amount as a strike',()=>{
 const source=payload([row()]);
 [source.columns[3],source.columns[5]]=[source.columns[5],source.columns[3]];
 expect(()=>readSavedActivity(source,{now})).toThrow(/checked/);
});
