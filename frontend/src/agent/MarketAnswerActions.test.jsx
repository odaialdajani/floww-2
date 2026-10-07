import React from 'react';
import {render,screen,fireEvent} from '@testing-library/react';
import AgentPanelAnswer from './AgentPanelAnswer';
import {checkedChartAction,isMarketQuestion,prepareScreenNavigation} from './chatNavigation';
const action={kind:'open_chart',view:'heatseeker',ticker:'NVDA',fact_ids:['vol-one']};
const answer={scope:'market',summary:'Cached examples from the full scan.',facts:[{id:'vol-one',ticker:'NVDA',metric:'Daily volume',value:7000,unit:'contracts',source:'Public',status:'degraded'}],actions:[action]};
test('market answer has a market label and verified current-chart button',()=>{const open=jest.fn();render(<AgentPanelAnswer turn={{turn_id:'one',status:'completed',ticker:null,answer}} onChartAction={open}/>);expect(screen.getByRole('heading',{name:'Market scan'})).toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'Open NVDA live chart'}));expect(open).toHaveBeenCalledWith(action);expect(screen.getByText(/original times and coverage/)).toBeInTheDocument();});
test.each([{...action,view:'public'},{...action,kind:'place_order'},{...action,ticker:'MSFT'},{...action,fact_ids:['missing']},{...action,ticker:'../orders'}])('untrusted action never becomes a chart button: %j',bad=>expect(checkedChartAction(bad,answer)).toBeNull());
test('malformed saved action list cannot crash the answer',()=>{render(<AgentPanelAnswer turn={{status:'completed',answer:{...answer,actions:{run:'shell'}}}}/>);expect(screen.getByRole('heading',{name:'Market scan'})).toBeInTheDocument();expect(screen.queryByRole('button',{name:/live chart/})).toBeNull();});
test.each(['Find unusual activity across all stocks','Scan every available ticker','Compare the whole market','Show unusual activity across all available data'])('whole-market wording is explicit: %s',q=>expect(isMarketQuestion(q)).toBe(true));
test('a stock-only question and negated full-scan request stay selected',()=>{expect(isMarketQuestion('Explain SPY')).toBe(false);expect(isMarketQuestion('Do not scan all stocks, only SPY')).toBe(false);});
test('screener navigation changes focus without losing saved filters',()=>{localStorage.setItem('th-prefs-v1',JSON.stringify({knobMinVol:400,universeOnly:false}));prepareScreenNavigation({page:'flowseeker-pro',ticker:'NVDA'});expect(JSON.parse(localStorage.getItem('th-prefs-v1'))).toEqual({knobMinVol:400,universeOnly:false,focusTicker:'NVDA'});});

test.each(['Find unusual activity across all the available stocks','Inspect all ETFs and funds','Scan all eligible tickers'])('broad stock wording stays explicit in the browser: %s',q=>expect(isMarketQuestion(q)).toBe(true));
