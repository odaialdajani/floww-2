import React from 'react';
import {expect,within,userEvent} from 'storybook/test';
import PublicPanel from '../PublicPanel';
import lifecycle from '../../fixtures/integration/lifecycle-inventory.v1.json';

const fixture={account:{ok:true,account_id:'STORY-ACCOUNT'},portfolio:{ok:true,account_id:'STORY-ACCOUNT',cash:100,buying_power:200,portfolio_value:500,positions:[]},orders:{ok:true,orders:[{order_id:'story-partial',symbol:'SPY261002C00500000',side:'BUY',quantity:3,filled_quantity:1,status:'PARTIAL'}]}};
const mockedReads=(failed,inventory=lifecycle.inventory)=>()=>{
 const original=window.fetch,prior=localStorage.getItem('floww_app_key');
 localStorage.setItem('floww_app_key','STORY-ONLY-NOT-A-CREDENTIAL');
 window.fetch=async(url,opts)=>String(url).includes('/api/public/')?{ok:!failed,status:failed?502:200,json:async()=>String(url).endsWith('/execution-lifecycle/inventory')?inventory:fixture[String(url).split('/').pop()]}:original(url,opts);
 return()=>{window.fetch=original;prior==null?localStorage.removeItem('floww_app_key'):localStorage.setItem('floww_app_key',prior);};
};
export default {title:'Public/Account reads',component:PublicPanel,beforeEach:mockedReads(false),
 parameters:{docs:{description:{component:'Synthetic account and fill response. No Public connection, entry approval, activation or broker transport.'}}},
 decorators:[Story=><div style={{background:'#0d222a',padding:16,color:'#d7e6e8'}}><Story/></div>]};
export const PartialFill={async play({canvasElement}){const c=within(canvasElement);await expect(await c.findByLabelText('Filled quantity for story-partial')).toHaveTextContent('1');await expect(c.getByLabelText('Remaining quantity for story-partial')).toHaveTextContent('2');}};
export const LocalLifecycleReview={async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(await c.findByText('Local lifecycle inventory · read-only'));await userEvent.click(c.getByRole('button',{name:'Read local lifecycle inventory'}));
 await expect(await c.findByRole('table',{name:'Process-local intent records'})).toHaveTextContent('UNKNOWN');
 await expect(c.getByRole('region',{name:'Local lifecycle review'})).toHaveTextContent('Account-wide limits UNSET');
 await expect(c.getByRole('region',{name:'Local lifecycle review'})).toHaveTextContent('not verified remote workflows');
}};
export const StorelessLifecycle={beforeEach:mockedReads(false,{...lifecycle.inventory,durable:false,storeless:true,intents:{n_known:0,n_open:0,n_unknown:0,open:[],unknown:[]},recovery:{durable_nonterminal_rows:null}}),async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(await c.findByText('Local lifecycle inventory · read-only'));await userEvent.click(c.getByRole('button',{name:'Read local lifecycle inventory'}));
 await expect(c.getByRole('region',{name:'Local lifecycle review'})).toHaveTextContent('Storeless; open broker inventory unknown');
}};
const controlledInventory={...lifecycle.inventory,...lifecycle.control_additions,protection:{...lifecycle.inventory.protection,...lifecycle.control_additions.protection}};
export const StoredControlReports={beforeEach:mockedReads(false,controlledInventory),async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(await c.findByText('Local lifecycle inventory · read-only'));await userEvent.click(c.getByRole('button',{name:'Read local lifecycle inventory'}));
 await expect(c.getByRole('region',{name:'Local lifecycle review'})).toHaveTextContent('4 stored approvals · 1 revoked');
 await expect(c.getByRole('region',{name:'Local lifecycle review'})).toHaveTextContent('Account policy installed · account-policy.v1');
 await expect(c.getByRole('table',{name:'Reported native protection support'})).toHaveTextContent('Unavailable');
}};
export const RecoveryReviewRequired={beforeEach:mockedReads(false,{...controlledInventory,intents:{n_known:0,n_open:0,n_unknown:0,open:[],unknown:[]}}),async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(await c.findByText('Local lifecycle inventory · read-only'));await userEvent.click(c.getByRole('button',{name:'Read local lifecycle inventory'}));
 await expect(c.getByRole('region',{name:'Local lifecycle review'})).toHaveTextContent('Recovery review required · RECOVERY_REQUIRED');
}};
export const SettledHistoryRecoverySurplus={beforeEach:mockedReads(false,{...controlledInventory,intents:{n_known:4,n_open:0,n_unknown:0,open:[],unknown:[]}}),async play({canvasElement}){
 const c=within(canvasElement);await userEvent.click(await c.findByText('Local lifecycle inventory · read-only'));await userEvent.click(c.getByRole('button',{name:'Read local lifecycle inventory'}));
 await expect(c.getByRole('region',{name:'Local lifecycle review'})).toHaveTextContent('Recovery review required · RECOVERY_REQUIRED');
 await expect(c.getByRole('region',{name:'Local lifecycle review'})).toHaveTextContent('4 process-local known records · 0 local open · 0 local unknown');
 await expect(c.getByRole('region',{name:'Local lifecycle review'})).toHaveTextContent('this read executes neither');
}};
export const AccountConnectionFailure={beforeEach:mockedReads(true),async play({canvasElement}){await expect(await within(canvasElement).findByTestId('public-panel-error')).toBeInTheDocument();}};
