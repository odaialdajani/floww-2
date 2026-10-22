import React from 'react';
import {fireEvent,render,screen} from '@testing-library/react';
import RecordedPriceChart from './RecordedPriceChart';

const frames=Array.from({length:120},(_,i)=>({time:new Date(Date.UTC(2026,9,1,13,30+i*30)).toISOString(),open:100+i,high:102+i,low:99+i,close:101+i,nodes:[]}));
let width;
beforeEach(()=>{width=800;jest.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(()=>({x:0,y:0,left:0,top:0,right:width,bottom:480,width,height:480,toJSON:()=>({})}));});
afterEach(()=>jest.restoreAllMocks());

test.each([1,2,3,120])('axis labels have bounded unique anchors for %i candles',count=>{
  render(<RecordedPriceChart ticker="SPY" frames={frames.slice(0,count)}/>);
  const labels=[...screen.getByTestId('recorded-price-chart').querySelectorAll('.recorded-time-label')];
  expect(labels.length).toBe(Math.min(5,count));
  expect(new Set(labels.map(t=>t.getAttribute('x'))).size).toBe(labels.length);
  if(count===1){expect(labels[0]).toHaveAttribute('text-anchor','middle');expect(+labels[0].getAttribute('x')).toBeCloseTo(368);}
  else{expect(labels[0]).toHaveAttribute('text-anchor','start');expect(labels.at(-1)).toHaveAttribute('text-anchor','end');}
  for(const label of labels){expect(label.childNodes[0].textContent.length).toBeLessThanOrEqual(16);expect(label.querySelector('title')).toHaveTextContent('New York');}
});
test('narrow chart uses fewer compact time labels without dropping the full selected date',()=>{
  width=300;render(<RecordedPriceChart ticker="SPY" frames={frames}/>);
  const labels=screen.getByTestId('recorded-price-chart').querySelectorAll('.recorded-time-label');
  expect(labels.length).toBeLessThanOrEqual(2);
  expect(screen.getByTestId('chart-reading-row')).toHaveTextContent('2026');
});
test('CVD keeps one concise coverage summary, with full methodology available on demand',()=>{
  const cvdLine=frames.map((f,i)=>({time:f.time,cvd:i%3===0?i*100:null}));
  render(<RecordedPriceChart ticker="SPY" frames={frames} cvdLine={cvdLine}/>);
  expect(screen.getByTestId('cvd-status')).toHaveTextContent('26/80');
  const method=screen.getByText(/Easley/);expect(method).not.toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'CVD method'}));expect(method).toBeVisible();
  expect(screen.getAllByTestId('cvd-point')).toHaveLength(26);
  fireEvent.click(screen.getByRole('button',{name:'Chart tools'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'Toggle CVD'}));
  expect(screen.queryByTestId('cvd-status')).not.toBeInTheDocument();
  expect(screen.queryByTestId('cvd-pane')).not.toBeInTheDocument();
});
test('Tools closes by Escape and explicit touch action, returning focus to its summary',()=>{
  render(<RecordedPriceChart ticker="SPY" frames={frames}/>);
  const tools=screen.getByRole('button',{name:'Chart tools'}),details=tools.closest('details');
  fireEvent.click(tools);const input=screen.getByRole('checkbox',{name:'Toggle VWAP'});input.focus();
  fireEvent.keyDown(input,{key:'Escape'});expect(details).not.toHaveAttribute('open');expect(tools).toHaveFocus();
  fireEvent.click(tools);fireEvent.click(screen.getByRole('button',{name:'Close chart tools'}));
  expect(details).not.toHaveAttribute('open');expect(tools).toHaveFocus();
});

// UI-03/04 control-band compaction: the readout collapses to two tight lines
// and the replay row stays one row — CSS contract pinned from the stylesheet
// bytes (real geometry proof lives in the live captures).
test('control band compaction rules exist (readout two-line, replay one-row)', () => {
  const fs = require('fs');
  const path = require('path');
  const css = fs.readFileSync(path.join(__dirname, 'RecordedPriceChart.css'), 'utf8');
  expect(css).toMatch(/recorded-chart-tools \.recorded-chart-readout\{[^}]*flex:0 1 auto/);
  expect(css).toMatch(/recorded-chart-tools \.recorded-chart-readout\{[^}]*flex-wrap:wrap/);
  expect(css).not.toMatch(/recorded-chart-tools \.recorded-chart-readout\{[^}]*overflow:hidden/);
  expect(css).toMatch(/recorded-chart-tools \.recorded-chart-readout > span\{[^}]*white-space:nowrap/);
  expect(css).toMatch(/recorded-chart-replay-row\{[^}]*white-space:nowrap/);
});
