import {cellPalette} from './SkylitHeatmapGrid';
import React from 'react';
import {render, fireEvent} from '@testing-library/react';
import SkylitHeatmapGrid from './SkylitHeatmapGrid';

test('signed palette keeps readable text at every sampled level',()=>{
 for(let i=0;i<=100;i++){
  const palette=cellPalette(i/100);
  expect(palette.contrast).toBeGreaterThanOrEqual(4.5);
  expect(palette.background).toMatch(/^rgb\(/);
  expect(['#000','#fff']).toContain(palette.foreground);
 }
});

test('asymmetric signed grid uses the Screener levels without changing values or selection',()=>{
 const expiry='2031-01-17', onCellClick=jest.fn();
 const data={grid:{expiries:[expiry],strikes:[100,101,102,103],grid:{[expiry]:{100:-40,101:100,102:0,103:null}}}};
 const {container}=render(<SkylitHeatmapGrid data={data} ticker="SPY" onCellClick={onCellClick} selected={{strike:100,expiry}} />);
 const negative=container.querySelector('td[data-r="3"][data-c="0"]');
 expect(negative.style.backgroundColor).toBe('rgb(55, 48, 107)');
 // jsdom does not parse repeating gradients; the compiled-browser check
 // verifies the actual hatch. Here assert its semantic presentation class.
 expect(negative.classList.contains('trin-negative')).toBe(true);
 expect(container.querySelector('.trin-legend-label').textContent).toBe('-$0.1K');
 expect(negative.getAttribute('aria-selected')).toBe('true');
 fireEvent.keyDown(negative,{key:'Enter'});
 expect(onCellClick).toHaveBeenCalledWith(100,expiry,-40);
 const zero=container.querySelector('.trin-zero'), missing=container.querySelector('.trin-missing');
 expect(zero.getAttribute('aria-label')).toContain('$0.0K');
 expect(missing.getAttribute('aria-label')).toContain('no data');
 expect(zero.style.backgroundColor).toBe('rgb(25, 25, 25)');
 expect(missing.style.backgroundColor).toBe('rgb(25, 25, 25)');
});
