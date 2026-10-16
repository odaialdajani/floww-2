/** @jest-environment jsdom */
import React from 'react';
import {render, screen, fireEvent} from '@testing-library/react';
import '@testing-library/jest-dom';
import SkylitHeatmapGrid from './SkylitHeatmapGrid';
import WallInspector from './WallInspector';
import {resolveSelectedWall} from '../../lib/solsticeSelection';

const expiry='2031-01-17';
function packet(){return {ticker:'SPY',spot:100,exposure_basis:'OI',grid:{expiries:[expiry],strikes:[110,105,100,95,90],grid:{[expiry]:{110:1,105:2,100:3,95:4,90:5}}},metrics:{walls:[],grids:{delta:{strikes:[100],expiries:[expiry],grid:{[expiry]:{100:2}}}}}};}

test('a cell that never had a classified wall is not a disappeared observation',()=>{
  expect(resolveSelectedWall(packet(),{ticker:'SPY',strike:110,wall_id:null})).toMatchObject({status:'unclassified',reason:'NO_CLASSIFIED_WALL',wall:null});
  expect(resolveSelectedWall(packet(),{ticker:'SPY',strike:110,wall_id:'gone'})).toMatchObject({status:'gone',reason:'WALL_GONE'});
});

test('raw and adjusted grids keep the explicitly shared strike population, including gaps',()=>{
  const data=packet();
  const {container}=render(<SkylitHeatmapGrid ticker="SPY" spot={100} data={data} metric="delta" axes={{strikes:data.grid.strikes,expiries:[expiry]}}/>);
  expect([...container.querySelectorAll('.trin-row')].map(r=>r.dataset.strike)).toEqual(['110','105','100','95','90']);
  expect(screen.getByRole('gridcell',{name:/110 by .*no data/})).not.toHaveTextContent('$0');
});

test('grid offers explicit price and selected-level centering without changing cells',()=>{
  const {container}=render(<SkylitHeatmapGrid ticker="SPY" spot={100} data={packet()} selected={{strike:95,expiry}}/>);
  const values=[...container.querySelectorAll('.trin-cell')].map(c=>c.textContent);
  fireEvent.click(screen.getByRole('button',{name:'Center on price'}));
  fireEvent.click(screen.getByRole('button',{name:'Show selected level'}));
  expect([...container.querySelectorAll('.trin-cell')].map(c=>c.textContent)).toEqual(values);
});

test('missing spot cannot create a centering target; absent selection has a concrete reason',()=>{
  render(<SkylitHeatmapGrid ticker="SPY" spot={null} data={packet()}/>);
  expect(screen.getByRole('button',{name:'Center on price'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Show selected level'})).toBeDisabled();
  expect(screen.getByRole('button',{name:'Show selected level'})).toHaveAttribute('title',expect.stringMatching(/Select a cell/));
});

test('the exposure overview offers an explicit return to the price region',()=>{
 const Profile=require('../triad/StrikeExposureProfile').default;
 render(<Profile data={packet()} basis="delta" wall={null} onSelect={jest.fn()}/>);
 expect(screen.getByRole('button',{name:'Center exposure profile on price'})).toBeEnabled();
});

test('selected-reading context stays visible while the review step changes',()=>{
  const ReviewInspector=require('./ReviewInspector').default;
  render(<ReviewInspector selectionKey="SPY|w" context={<p>SPY · 100 · 2031-01-17</p>} wall={<p>Wall facts</p>} contract={<p>Contract facts</p>}/>);
  expect(screen.getByRole('group',{name:'Selected reading'})).toHaveTextContent('SPY · 100');
  fireEvent.click(screen.getByRole('tab',{name:'Contract'}));
  expect(screen.getByRole('group',{name:'Selected reading'})).toBeVisible();
});

test('wall detail is available on demand, after the decision-critical reading',()=>{
  render(<WallInspector wall={{wall_id:'above',low:105,high:110,members:[105,110]}}/>);
  expect(screen.getByText('Exposure details and coverage').closest('details')).not.toHaveAttribute('open');
});

test('wall inspection does not invent generic confirmation or invalidation without a selected scenario',()=>{
  render(<WallInspector wall={{wall_id:'above',low:105,high:110,members:[105,110]}}/>);
  expect(screen.getByTestId('wall-inspector')).toHaveTextContent('Confirmation not supplied');
  expect(screen.getByTestId('wall-inspector')).toHaveTextContent('Invalidation not supplied');
  expect(screen.getByTestId('wall-inspector')).not.toHaveTextContent('reclaim and hold above zone');
});
