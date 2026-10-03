import React from 'react';
import {expect,within} from 'storybook/test';
import PublicPanel from '../PublicPanel';

const fixture={account:{ok:true,account_id:'STORY-ACCOUNT'},portfolio:{ok:true,account_id:'STORY-ACCOUNT',cash:100,buying_power:200,portfolio_value:500,positions:[]},orders:{ok:true,orders:[{order_id:'story-partial',symbol:'SPY261002C00500000',side:'BUY',quantity:3,filled_quantity:1,status:'PARTIAL'}]}};
const mockedReads=failed=>()=>{
 const original=window.fetch,prior=localStorage.getItem('floww_app_key');
 localStorage.setItem('floww_app_key','STORY-ONLY-NOT-A-CREDENTIAL');
 window.fetch=async(url,opts)=>String(url).includes('/api/public/')?{ok:!failed,status:failed?502:200,json:async()=>fixture[String(url).split('/').pop()]}:original(url,opts);
 return()=>{window.fetch=original;prior==null?localStorage.removeItem('floww_app_key'):localStorage.setItem('floww_app_key',prior);};
};
export default {title:'Public/Account reads',component:PublicPanel,beforeEach:mockedReads(false),
 parameters:{docs:{description:{component:'Synthetic account and fill response. No Public connection, entry approval, activation or broker transport.'}}},
 decorators:[Story=><div style={{background:'#0d222a',padding:16,color:'#d7e6e8'}}><Story/></div>]};
export const PartialFill={async play({canvasElement}){const c=within(canvasElement);await expect(await c.findByLabelText('Filled quantity for story-partial')).toHaveTextContent('1');await expect(c.getByLabelText('Remaining quantity for story-partial')).toHaveTextContent('2');}};
export const AccountConnectionFailure={beforeEach:mockedReads(true),async play({canvasElement}){await expect(await within(canvasElement).findByTestId('public-panel-error')).toBeInTheDocument();}};
