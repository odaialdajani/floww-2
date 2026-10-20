import React from 'react';
import {fireEvent,render,screen} from '@testing-library/react';
import axios from 'axios';
import SavedChartReadings from './SavedChartReadings';
jest.mock('axios',()=>({get:jest.fn()}));
test('saved options rows distinguish second and snapshot identity and open the named replay explicitly',async()=>{
 const decisions=[7,8].map(n=>({decision_id:'dec_'+n,ticker:'SPY',at_ts:`2026-10-19T13:30:0${n}Z`,snapshot_id:'snapshot_'+n,n_quotes:20,features_status:'available'}));
 axios.get.mockResolvedValue({data:{ticker:'SPY',order:'newest',decisions,count:2,status:'available',has_more:false,next_cursor:null}});
 const open=jest.fn();render(<SavedChartReadings ticker="SPY" onOpen={open}/>);
 const toggle=screen.getByRole('button',{name:'Saved option readings'});fireEvent.click(toggle);
 expect(await screen.findByText(/9:30:07 AM/)).toBeVisible();expect(screen.getByText(/9:30:08 AM/)).toBeVisible();
 expect(screen.getByText('Snapshot snapshot_7')).toBeVisible();
 const actions=screen.getAllByRole('button',{name:'Open saved options snapshot'});fireEvent.click(actions[0]);
 expect(open).toHaveBeenCalledWith('snapshot_7');expect(toggle).toHaveAttribute('aria-expanded','false');
 fireEvent.click(toggle);const first=await screen.findByRole('button',{name:'First saved'});first.focus();
 fireEvent.keyDown(first,{key:'Escape'});expect(toggle).toHaveFocus();expect(toggle).toHaveAttribute('aria-expanded','false');
});
