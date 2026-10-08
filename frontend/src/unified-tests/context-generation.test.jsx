/* U09 selection/generation context continuity matrix (synthetic records only).
   No model invocation, no network (fetch injected), no order surfaces. */
import {act,renderHook} from '@testing-library/react';
import {useScopedReading} from '../hooks/useScopedReading';
import {parseChatNavigation,verifyNavigationTicker,checkedChartAction,prepareScreenNavigation,isMarketQuestion} from '../agent/chatNavigation';

test('navigation-only phrases resolve to pages; research questions stay null',()=>{
 expect(parseChatNavigation('show me the options map')).toEqual({page:'skylit',label:'Options map'});
 expect(parseChatNavigation('open market view for SPY')).toEqual({page:'trinity',ticker:'SPY',label:'Market view'});
 expect(parseChatNavigation('find $NVDA screener')).toEqual({page:'flowseeker-pro',ticker:'NVDA',label:'Screener'});
 expect(parseChatNavigation('what does this unusual call buying mean?')).toBeNull();
 expect(parseChatNavigation('x'.repeat(2001))).toBeNull();
 expect(parseChatNavigation('show me saved answers')).toEqual({history:true,label:'Saved answers'});
});

test('ticker-qualified navigation never invents grounding',async()=>{
 // Bare multi-word names resolve exactly and never bind pseudo-tickers:
 // "show me the stock chart" opens the chart with no ticker (the `chart`
 // key can no longer claim the word "stock").
 expect(parseChatNavigation('show me the stock chart')).toEqual({page:'heatseeker',label:'Stock chart'});
 // A failed catalog lookup still fails closed downstream.
 await expect(verifyNavigationTicker('STOCK',async()=>({ok:true,json:async()=>({asof:'g1',instruments:[{symbol:'SPY'}],has_more:false,complete_provider_catalog:true,stale:false})}))).rejects.toThrow("not in the provider's available stock list");
 // Overlong symbols refuse at parse time (12-char bound).
 expect(parseChatNavigation('open stock chart for FAKETICKER123')).toBeNull();
 expect(parseChatNavigation('show me the options map')).toEqual({page:'skylit',label:'Options map'});
});

test('chart actions need exact grounded facts or they are refused',()=>{
 const answer={facts:[{id:'f1',ticker:'SPY'},{id:'f2',ticker:'SPY'}]};
 expect(checkedChartAction({kind:'open_chart',view:'heatseeker',ticker:'SPY',fact_ids:['f1']},answer))
  .toEqual({page:'heatseeker',ticker:'SPY',label:'Stock chart'});
 expect(checkedChartAction({kind:'open_chart',view:'heatseeker',ticker:'QQQ',fact_ids:['f1']},answer)).toBeNull();
 expect(checkedChartAction({kind:'open_chart',view:'heatseeker',ticker:'SPY',fact_ids:Array.from({length:31},(_,i)=>'f'+i)},answer)).toBeNull();
 expect(checkedChartAction({kind:'open_chart',view:'skylit',ticker:'SPY',fact_ids:['f1']},answer)).toBeNull();
 expect(checkedChartAction({kind:'open_chart',view:'heatseeker',ticker:'SPY',fact_ids:['missing']},answer)).toBeNull();
});

test('ticker verification confirms, refuses unknown, and reports incomplete lists',async()=>{
 const catalog=(symbols,extra={})=>async()=>({ok:true,json:async()=>({asof:'g1',instruments:symbols.map(symbol=>({symbol})),has_more:false,complete_provider_catalog:true,stale:false,...extra})});
 await expect(verifyNavigationTicker('SPY',catalog(['SPY','QQQ']))).resolves.toBe('SPY');
 await expect(verifyNavigationTicker('FAKE',catalog(['SPY']))).rejects.toThrow("not in the provider's available stock list");
 await expect(verifyNavigationTicker('SPY',catalog(['QQQ'],{complete_provider_catalog:false}))).rejects.toThrow('incomplete');
 await expect(verifyNavigationTicker('spy',catalog(['SPY']))).rejects.toThrow('valid stock symbol');
});

test('screener handoff saves focus; corrupt prefs raise a friendly error',()=>{
 localStorage.clear();
 prepareScreenNavigation({page:'flowseeker-pro',ticker:'SPY'});
 expect(JSON.parse(localStorage.getItem('th-prefs-v1')).focusTicker).toBe('SPY');
 localStorage.setItem('th-prefs-v1','{broken');
 expect(()=>prepareScreenNavigation({page:'flowseeker-pro',ticker:'SPY'})).toThrow('could not be saved');
 expect(prepareScreenNavigation({page:'heatseeker',ticker:'SPY'})).toBeUndefined();
 localStorage.clear();
});

test('scoped reading keeps generations apart and restores retained context',()=>{
 const {result,rerender}=renderHook(({scope})=>useScopedReading(scope,{retain:true}),{initialProps:{scope:'SPY:chart'}});
 act(()=>result.current[1]({ticker:'SPY',event_time:'t0',price:650}));
 rerender({scope:'QQQ:chart'});
 expect(result.current[0]).toBeNull();
 rerender({scope:'SPY:chart'});
 expect(result.current[0]).toEqual({ticker:'SPY',event_time:'t0',price:650});
 expect(result.current[2]).toBe(true);
});

test('market-wide wording is detected; exclusions stay research',()=>{
 expect(isMarketQuestion('scan all available stocks for unusual flow')).toBe(true);
 expect(isMarketQuestion('do not scan all the stocks, just SPY')).toBe(false);
 expect(isMarketQuestion('what is gamma?')).toBe(false);
});
