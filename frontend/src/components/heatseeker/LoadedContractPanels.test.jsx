import React from 'react';
import {render,screen,fireEvent} from '@testing-library/react';
import LoadedContractPanels,{OpenInterestPanel,CallPutLadder} from './LoadedContractPanels';

const data={ticker:'SPY',spot:500,formula_version:'gex.v2',grid:{oi_surface:{version:'oi-counts.v1',units:'contracts',status:'partial',
 strikes:[500,501],expiries:['2026-10-30'],oi_effective_dates:[],cells:{'2026-10-30':{'500':{call:0,put:null,total:null,missing:1,invalid:0,quarantined:0},
 '501':{call:5,put:7,total:12,missing:0,invalid:0,quarantined:0}}}}},strikes:[{strike:500,call_gex:25,put_gex:null},{strike:501,call_gex:0,put_gex:-100}]};

test('counts keep measured zero and unknown distinct, with explicit units and date gap',()=>{
 render(<OpenInterestPanel data={data}/>);
 expect(screen.getByText(/OI effective date unknown/)).toBeInTheDocument();
 const row=screen.getByRole('row',{name:/500/});
 expect(row).toHaveTextContent('0');expect(row).toHaveTextContent('—');
 expect(screen.getByText('12')).toBeInTheDocument();
 expect(screen.getByText(/contracts · loaded scope/)).toBeInTheDocument();
});
test('older records do not rebuild absent OI',()=>{
 render(<OpenInterestPanel data={{strikes:[{strike:500,call_oi:9}]}}/>);
 expect(screen.getByRole('status')).toHaveTextContent(/not recorded/);
 expect(screen.queryByRole('table')).not.toBeInTheDocument();
});
test('a strike absent from the selected expiry is not a loaded reading',()=>{
 const value=JSON.parse(JSON.stringify(data));
 delete value.grid.oi_surface.cells['2026-10-30']['500'];
 render(<OpenInterestPanel data={value}/>);
 expect(screen.getByRole('row',{name:/500/})).toHaveTextContent('No loaded contracts for this expiry');
});
test('ladder uses one magnitude scale, keeps unknown leg and real zero',()=>{
 render(<CallPutLadder data={data}/>);
 expect(screen.getByLabelText('Call exposure 500')).toHaveStyle({width:'25%'});
 expect(screen.getByLabelText('Put exposure 501')).toHaveStyle({width:'100%'});
 expect(screen.getByLabelText('Call exposure 501')).toHaveStyle({width:'0%'});
 expect(screen.getByText('Put exposure unavailable')).toBeInTheDocument();
});
test('secondary panels start closed and use the supplied observation only',()=>{
 render(<LoadedContractPanels data={data}/>);
 expect(screen.queryByRole('table')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Open interest',exact:true}));
 expect(screen.getByRole('table')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Call / put ladder',exact:true}));
 expect(screen.getByRole('table')).toHaveAccessibleName('Loaded call and put exposure');
});
