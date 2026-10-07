import React from 'react';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import AppShell from '../shell/AppShell';
import SkylitDashboard from '../components/heatseeker/SkylitDashboard';
import OptionsChainTable from '../components/OptionsChainTable';
import useScreenContext from './useScreenContext';
function ReadSelection(){const [context]=useScreenContext();return <output data-testid="lifecycle-selection">{JSON.stringify(context)}</output>;}
const selection=()=>JSON.parse(screen.getByTestId("lifecycle-selection").textContent);
import axios from 'axios';
import {fetchPublicChain} from '../lib/publicApi';
jest.mock('axios',()=>({get:jest.fn(),post:jest.fn()}));
jest.mock('../lib/publicApi',()=>({fetchPublicChain:jest.fn()}));
jest.mock('../agent/AgentModelSettings',()=>()=>null);
jest.mock('../shell/Sidebar',()=>()=>null);
jest.mock('react-plotly.js',()=>()=>null);
jest.mock('../components/heatseeker/SkylitTickerBar',()=>()=>null);
jest.mock('../components/heatseeker/SkylitControlBar',()=>()=>null);
jest.mock('../components/heatseeker/SkylitHeatmapGrid',()=>()=> <button data-testid='lifecycle-map-focus'>Focus map</button>);
jest.mock('../components/heatseeker/SkylitMetricsSidebar',()=>()=>null);
jest.mock('../components/heatseeker/ExposureStrip',()=>()=>null);
jest.mock('../components/heatseeker/StockDirectory',()=>()=>null);
jest.mock('../components/heatseeker/PriceNodeHistory',()=>()=>null);
jest.mock('../components/heatseeker/ReplayStrip',()=>()=>null);
jest.mock('../components/flowseeker/AlertEngineStrip',()=>()=>null);
beforeAll(()=>Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true}));
test('grid to chain switch must not submit the previous ticker and expiry context',async()=>{
 axios.get.mockResolvedValue({data:{decisions:[],rows:[]}});
 fetchPublicChain.mockImplementation(async ticker=>({ticker,contracts:[],expiries:['2026-10-02'],n_contracts:0}));
 let submitted;
 global.fetch=jest.fn(async(url,options)=>({ok:true,json:async()=>{
  if(String(url).endsWith('/session'))return {};
  if(String(url).endsWith('/ask')){submitted=JSON.parse(options.body);return {turn_id:'test-turn'};}
  return {turn_id:'test-turn',status:'completed',ticker:submitted.ticker,horizon:submitted.horizon,text:'Synthetic saved answer for '+submitted.ticker};
 }}));
 const map={ticker:'SPY',snapshotId:'map-SPY',data_source:'public_api',formula_version:'gex.v2',asof:'2026-09-27T14:00:00Z',event_time:'2026-09-27T13:59:50Z',map_query:{expiries:4,mode:'day',dte:0},strikes:[{strike:650}],grid:{strikes:[650],expiries:['2026-09-28'],grid:{'2026-09-28':{'650':123}}}};
 const view=render(<AppShell page='heatseeker'><SkylitDashboard defaultStudy='options' ticker='SPY' dte={0} data={map} spot={650}/><ReadSelection/></AppShell>);
 await act(async()=>{});
 expect(selection()).toMatchObject({contextVersion:2,ticker:"SPY",snapshotId:"map-SPY",dte:"0dte"});
 // App.js uses this same conditional lifecycle: chain replaces SkylitDashboard while AppShell stays mounted.
 view.rerender(<AppShell page='heatseeker'><h1>Visible ticker QQQ</h1><OptionsChainTable ticker='QQQ' spot={500}/><ReadSelection/></AppShell>);
 await waitFor(()=>expect(fetchPublicChain).toHaveBeenCalledWith('QQQ',expect.anything()));
 await screen.findByText(/Options Chain/);
 fireEvent.change(screen.getByRole('option',{name:'All Expiries'}).parentElement,{target:{value:'2026-10-02'}});
 await act(async()=>{});
 fireEvent.click(screen.getByRole('button',{name:'Open Ask FLOWW'}));
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'What changed?'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await screen.findByText("Choose a ticker in Screener, Options map or Unusual flow before asking.");
 expect(global.fetch.mock.calls.some(([url])=>String(url).endsWith('/ask'))).toBe(false);
 // Default price focus asks about the chosen stock only. It carries no
 // selected option expiry, historical-price evidence or made-up map identity.
 view.rerender(<AppShell page='heatseeker'><SkylitDashboard ticker='QQQ' dte={7} data={{...map,ticker:'QQQ'}} spot={500}/><ReadSelection/></AppShell>);
 await act(async()=>{});
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'What changed now?'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(submitted).toBeDefined());
 expect(submitted.ticker).toBe('QQQ');
 expect(submitted.horizon).toBe('all');
 expect(submitted.screen).toMatchObject({contextVersion:1,page:'heatseeker',ticker:'QQQ',study:'Price chart',navigationOnly:true,observedAt:null});
 for(const field of ['snapshotId','mapVersion','mapQuery','mapExpiries','selectedStrike','selectedExpiry','displayMode'])expect(submitted.screen).not.toHaveProperty(field);
 await screen.findByText('Synthetic saved answer for QQQ');
 // An explicitly focused, fully qualified map still submits its own version-two
 // context and the chosen option horizon; the navigation fallback cannot replace it.
 const currentMap={...map,ticker:'QQQ',snapshotId:'map-QQQ',map_query:{...map.map_query,dte:7}};
 view.rerender(<AppShell page='heatseeker'><SkylitDashboard key='selected-map' defaultStudy='options' ticker='QQQ' dte={7} data={currentMap} spot={500}/><ReadSelection/></AppShell>);
 await act(async()=>{});
 fireEvent.click(screen.getAllByTestId('lifecycle-map-focus')[0]);
 const currentSelection=selection();expect(currentSelection).toMatchObject({contextVersion:2,ticker:'QQQ',snapshotId:'map-QQQ',dte:'days:7'});
 expect(currentSelection.mapQuery).toEqual(currentMap.map_query);expect(currentSelection.mapVersion).toBe(currentMap.asof);
 expect(currentSelection.mapExpiries).toEqual(currentMap.grid.expiries);
 submitted=undefined;
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'What changed in this selected map?'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(submitted).toBeDefined());
 expect(submitted.ticker).toBe('QQQ');expect(submitted.horizon).toBe('days:7');
 expect(submitted.screen).toEqual(currentSelection);
});
