import React from 'react';
import {render,screen} from '@testing-library/react';
import WallInspector from './WallInspector';
const wall={wall_id:'w',low:100,high:100,members:[100],gross:1000,net:1000};
const row=label=>screen.getByText(label).closest('tr');

test('missing inputs are unavailable while measured zero and partial warnings remain visible',()=>{
 const props={wall,metrics:{wall_metrics:{w:{daddex_gross:0,daddex_net:0,daddex_usable:0,daddex_missing:2,
   volume_gross:0,volume_net:0,volume_n:0,volume_usable:0,volume_missing:2,volume_invalid:0}}}};
 const mounted=render(<WallInspector {...props}/>);
 expect(row('Δ gross / net').textContent).not.toContain('$0');
 expect(row('Session activity').textContent).not.toContain('$0');
 const measured={...props.metrics.wall_metrics.w,daddex_usable:1,daddex_missing:1,volume_usable:1,volume_missing:1};
 mounted.rerender(<WallInspector wall={wall} metrics={{wall_metrics:{w:measured}}}/>);
 expect(row('Δ gross / net').textContent).toContain('$0 / $0');
 expect(row('Δ gross / net').textContent).toContain('1 δ-missing');
 expect(row('Session activity').textContent).toContain('$0 / $0');
 expect(row('Session activity').textContent).toContain('1 volume missing');
});

test('VEX contract gross is not replaced by the absolute net cell sum',()=>{
 render(<WallInspector wall={wall} displayGrid={{vex_grid:{'2030-01-15':{'100':0,'999':5000}},
  vex_strike_gross:[{strike:100,vex_gross:200},{strike:999,vex_gross:9999}],vex_meta:{status:'ok',model:'local-bs-vanna.v1'}}}/>);
 expect(row('VEX gross / net').textContent).toContain('$200 / $0');
 expect(row('VEX gross / net').textContent).toContain('local-bs-vanna.v1');
 expect(row('VEX gross / net').textContent).not.toContain('9999');
});

test('an older grid without contract gross keeps that amount unavailable',()=>{
 render(<WallInspector wall={wall} displayGrid={{vex_grid:{'2030-01-15':{'100':25}},vex_meta:{status:'ok'}}}/>);
 expect(row('VEX gross / net').textContent).toContain('— / $25');
 expect(row('VEX gross / net').textContent).toContain('gross unavailable');
});


test('repeated wall members do not repeat either expiry contributions or VEX net',()=>{
 render(<WallInspector wall={{...wall,members:[100,100,'100']}}
  grids={{delta:{grid:{'2030-01-15':{'100':25}}}}}
  displayGrid={{vex_grid:{'2030-01-15':{'100':25}},vex_strike_gross:[{strike:100,vex_gross:100}],vex_meta:{status:'ok'}}}/>);
 expect(row('VEX gross / net').textContent).toContain('$100 / $25');
 expect(screen.getByText('Per-expiry').closest('div').textContent).toContain('$25');
 expect(screen.getByText('Per-expiry').closest('div').textContent).not.toContain('$75');
});

test('partial member and scope input coverage remain visible beside VEX values',()=>{
 render(<WallInspector wall={{...wall,members:[100,101]}} displayGrid={{
  vex_grid:{'2030-01-15':{'100':0}},vex_strike_gross:[{strike:100,vex_gross:100}],
  vex_meta:{status:'ok',missing_vanna_inputs:2,quarantined:1,invalid_type:1}}}/>);
 const text=row('VEX gross / net').textContent;
 expect(text).toContain('1/2 member strikes');
 expect(text).toContain('scope: 2 missing inputs, 1 quarantined, 1 invalid types');
 expect(text).toContain('$100 / $0');
});

test.each([Infinity,NaN,'',false,'bad'])('malformed amounts never become dollar values: %s',value=>{
 render(<WallInspector wall={{...wall,gross:value,net:value}} metrics={{wall_metrics:{w:{
  daddex_gross:value,daddex_net:value,daddex_usable:1,daddex_missing:0,
  volume_gross:value,volume_net:value,volume_usable:1,volume_n:1}}}}/>);
 for(const label of ['Raw gross / net','Δ gross / net','Session activity']) {
  expect(row(label).textContent).toContain('— / —');
  expect(row(label).textContent).not.toContain('$');
 }
});

test('finite cells overflowing the wall sum stay unavailable',()=>{
 render(<WallInspector wall={{...wall,members:[100,101]}} displayGrid={{
  vex_grid:{'2030-01-15':{'100':Number.MAX_VALUE,'101':Number.MAX_VALUE}},
  vex_strike_gross:[{strike:100,vex_gross:Number.MAX_VALUE},{strike:101,vex_gross:Number.MAX_VALUE}]}}/>);
 expect(row('VEX gross / net').textContent).toContain('— / —');
 expect(row('VEX gross / net').textContent).not.toContain('Infinity');
});
