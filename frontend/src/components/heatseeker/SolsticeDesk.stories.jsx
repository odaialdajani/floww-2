import React from 'react';
import axios from 'axios';
import {expect,userEvent,within} from 'storybook/test';
import fixture from '../../fixtures/integration/solstice-display.v1.json';
import SkylitDashboard from './SkylitDashboard';
import ReplayStrip from './ReplayStrip';

const mockReads=()=>{
 const original=axios.get;
 axios.get=async url=>({data:String(url).includes('/manifest/')?{day:'2026-10-02',snapshots:[{id:fixture.display.snapshotId,asof:fixture.display.asof}],gaps:[{reason:'MISSING_CAPTURE'}]}:
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
export const ReplayGap={render:()=> <ReplayStrip ticker="SPY" onReplay={()=>{}}/>,async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(c.getByTestId('solstice-replay-load'));
 await expect(c.getByTestId('solstice-replay-strip')).toHaveTextContent('gaps');
}};
