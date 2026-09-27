import React from 'react';
import {render,screen} from '@testing-library/react';
import BarHeatmap from './BarHeatmap';
const bars=container=>container.querySelectorAll('.bar-row [style*="border-radius"]');
const sample={spot:100,strikes:[{strike:100,gex:900000,vex:0,charm:null}],nodes:{king:{strike:100}}};
test.each(['vex','charm'])('%s cannot inherit another measurement',mode=>{
 const {container}=render(<BarHeatmap data={sample} viewMode={mode}/>);
 expect(bars(container)).toHaveLength(0);
 expect(container.textContent).toContain(mode==='vex'?'0':'Unavailable');
});
test('the selected canonical grid controls sign even if a legacy strike value disagrees',()=>{
 const data={...sample,strikes:[{strike:100,gex:900000,vex:123}],grid:{expiries:['a','b'],vex_grid:{a:{100:-50},b:{100:-25}}}};
 const {container}=render(<BarHeatmap data={data} viewMode='vex'/>);
 const row=screen.getByLabelText('100 VEX: -75');
 expect(bars(container)).toHaveLength(1);
 expect(row.querySelector('.justify-end [style*="border-radius"]')).toBeTruthy();
 expect(row.querySelector('.text-amber-300')).toBeNull();
});
test('incomplete selected expiry coverage is unavailable, never a surviving subtotal',()=>{
 const data={...sample,grid:{expiries:['a','b'],vex_grid:{a:{100:50},b:{100:null}}}};
 const {container}=render(<BarHeatmap data={data} viewMode='vex'/>);
 expect(bars(container)).toHaveLength(0);
 expect(screen.getByText('Unavailable')).toBeInTheDocument();
});
test('zero remains known and magnitude filtering uses selected values only',()=>{
 const data={...sample,strikes:[{strike:100,gex:900000,vex:0},{strike:101,gex:1,vex:-40}]};
 const {container}=render(<BarHeatmap data={data} viewMode='vex' filters={{magMin:20}}/>);
 expect(container.querySelectorAll('.bar-row')).toHaveLength(1);
 expect(screen.getByLabelText('101 VEX: -40')).toBeInTheDocument();
});
test('zero GEX has no directional bar, and missing GEX remains unavailable',()=>{
 const {container}=render(<BarHeatmap data={{spot:100,strikes:[{strike:100,gex:0},{strike:101,gex:null}]}}/>);
 expect(bars(container)).toHaveLength(0);
 expect(screen.getByText('Unavailable')).toBeInTheDocument();
});

test('selected measurement retains expiry columns absent from raw GEX axes',()=>{
 const data={...sample,grid:{expiries:['a'],vex_grid:{a:{100:50},b:{100:-200}}}};
 render(<BarHeatmap data={data} viewMode='vex'/>);
 expect(screen.getByLabelText('100 VEX: -150')).toBeInTheDocument();
});
