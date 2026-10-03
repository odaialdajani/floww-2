import React from 'react';
import axios from 'axios';
import {expect,userEvent,within} from 'storybook/test';
import fixture from '../../fixtures/integration/solstice-display.v1.json';
import SkylitDashboard from './SkylitDashboard';
import ReplayStrip from './ReplayStrip';
import ExpiryCoverage from './ExpiryCoverage';
import coverage from '../../fixtures/integration/coverage-read.v1.json';

const mockReads=({parameters={}}={})=>{
 const original=axios.get;
 axios.get=async url=>({data:String(url).includes('/manifest/')?{day:'2026-10-02',snapshots:[{id:fixture.display.snapshotId,asof:fixture.display.asof}],gaps:[{reason:'MISSING_CAPTURE'}]}:
  String(url).includes('/price-paths/sessions')?(parameters.coverageSessions || coverage.sessions):
  String(url).includes('/price-paths/expiries')?parameters.coverageRefusal?await Promise.reject({response:{status:502,data:coverage.refused_expiries}}):(parameters.coverageExpiries || coverage.expiries):
  String(url).includes('/price-paths/comparable')?coverage.refused_comparison:
  String(url).includes('/attribute/')?{ticker:'SPY',status:'ok',from:{id:'fixture-baseline'},to:{id:'fixture-current'},strike_deltas:[]}:
  String(url).includes('/replay/')?fixture.replay:String(url).includes('recorder_health')?{worker_state:'wired_off',store:{durable:false,backing:'memory'}}:{snapshots:[],decisions:[],rows:[],tickers:[]}});
 return()=>{axios.get=original;};
};
export default {title:'Solstice/Production desk',component:SkylitDashboard,beforeEach:mockReads,
 args:{ticker:'SPY',spot:fixture.display.spot,data:fixture.display},
 decorators:[Story=><div style={{height:700,minWidth:0}}><Story/></div>],
 parameters:{layout:'fullscreen',docs:{description:{component:'Actual production desk with the committed R14 backend-generated synthetic display envelope. No preview analytics, provider call, broker or durable live recorder is used.'}}}};
export const MatrixAndProfile={async play({canvasElement}){
 const c=within(canvasElement);
 await expect(c.getByLabelText('Canvas layout')).toHaveValue('profile');
 await expect(c.getByTestId('skylit-profile-header')).toBeInTheDocument();
}};
export const Waiting={args:{data:{...fixture.display,quality:{state:'partial',setupEligible:false,reasonCodes:['PRICE_CONFIRMATION_REQUIRED']}}}};
export const MissingSameDayExpiry={args:{dte:0,data:{...fixture.display,strikes:[],grid:{strikes:[],expiries:[],grid:{}},scope_selection:{status:'unavailable'},quality:{state:'unavailable',setupEligible:false,reasonCodes:['NO_LISTED_SAME_SESSION_EXPIRY']}}}};
export const MissingActivity={args:{data:{...fixture.display,metrics:{...fixture.display.metrics,grids:{...fixture.display.metrics.grids,session_delta_volume:{status:'unavailable',reason:'VOLUME_OR_GREEKS_MISSING'}}}}},async play({canvasElement}){
 const c=within(canvasElement);await userEvent.selectOptions(c.getByLabelText('GEX basis'),'session_delta_volume');
 await expect(c.getByTestId('skylit-metric-unavailable')).toHaveTextContent('unavailable');
}};
export const StoredSessions={render:()=> <ReplayStrip ticker="SPY" onReplay={()=>{}}/>,async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(c.getByRole('button',{name:'Stored sessions'}));
 await expect(c.getByLabelText('Recorded sessions')).toBeInTheDocument();
 await userEvent.selectOptions(c.getByLabelText('Recorded sessions'),'2026-10-02');
 await expect(c.getByLabelText('Stored session date')).toHaveValue('2026-10-02');
}};
export const OvernightStoredDay={...StoredSessions,parameters:{coverageSessions:coverage.overnight_sessions},async play(context){
 await StoredSessions.play(context);const c=within(context.canvasElement);
 await expect(c.getByTestId('solstice-session-attribution')).toHaveTextContent('Stored day 2026-10-02 · NY date 2026-10-01');
 await expect(c.getByTestId('solstice-session-attribution')).toHaveTextContent('Overnight');
}};
export const ComparisonRefused={render:()=> <ReplayStrip ticker="SPY"/>,async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(c.getByTestId('solstice-compare-btn'));
 await expect(c.getByTestId('solstice-replay-strip')).toHaveTextContent('SCOPE_MISMATCH');
 await expect(c.queryByTestId('solstice-compare-result')).not.toBeInTheDocument();
}};
export const ListedRangeAdmission={render:()=> <ExpiryCoverage ticker="SPY"/>,async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(c.getByText('Listed 14–60 DTE coverage'));
 await userEvent.click(c.getByRole('button',{name:'Read listed coverage'}));
 await expect(c.getByRole('table',{name:'Listed expiry admission'})).toHaveTextContent('28 DTE');
}};
const cappedRows=Array.from({length:12},(_,index)=>({expiry:`2026-10-${String(16+index).padStart(2,'0')}`,dte:14+index,admitted:true,reason:'ADMITTED',display_envelope:true}));
export const CappedExpiryListing={...ListedRangeAdmission,parameters:{coverageExpiries:{...coverage.expiries,expiries:cappedRows,n_admitted:12,coverage:{requested_expiries:12,n_listed:12,n_display_envelope:12,listing_capped:true,lower_edge_observed:false,upper_edge_observed:false}}},async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(c.getByText('Listed 14–60 DTE coverage'));await userEvent.click(c.getByRole('button',{name:'Read listed coverage'}));
 await expect(c.getByTestId('solstice-expiry-coverage')).toHaveTextContent('Listing capped');
 await expect(c.getByTestId('solstice-expiry-coverage')).toHaveTextContent('Lower edge not observed');
}};
export const ChainReadRefused={...ListedRangeAdmission,parameters:{coverageRefusal:true},async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(c.getByText('Listed 14–60 DTE coverage'));await userEvent.click(c.getByRole('button',{name:'Read listed coverage'}));
 await expect(c.getByTestId('solstice-expiry-coverage')).toHaveTextContent('chain_unavailable');
 await expect(c.queryByRole('table')).not.toBeInTheDocument();
}};
export const HistoricalRangeUnavailable={render:()=> <ExpiryCoverage ticker="SPY" replay/>,async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(c.getByText('Listed 14–60 DTE coverage'));
 await expect(c.getByRole('button',{name:'Read listed coverage'})).toBeDisabled();
 await expect(c.getByTestId('solstice-expiry-coverage')).toHaveTextContent('recorded dates');
}};
export const ReplayGap={render:()=> <ReplayStrip ticker="SPY" onReplay={()=>{}}/>,async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(c.getByTestId('solstice-replay-load'));
 await expect(c.getByTestId('solstice-replay-strip')).toHaveTextContent('gaps');
}};
