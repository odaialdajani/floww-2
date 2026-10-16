import React from 'react';
import {fireEvent, render, screen} from '@testing-library/react';
import RecordedPriceChart from './RecordedPriceChart';

const frame = (minute, volume = 10) => ({time:`2026-10-06T13:${String(30+minute).padStart(2,'0')}:00Z`,open:100,high:102,low:99,close:101,volume,nodes:[]});
const symbol = 'SPY261017C00650000';
const premium = (minute, c) => ({t:frame(minute).time,c});
const plot = (frames, contractBars) => <RecordedPriceChart ticker="SPY" frames={frames} contractSymbol={symbol} contractBars={contractBars} contractStatus="available" />;

beforeEach(() => {
  jest.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockReturnValue({left:0,top:0,width:800,height:480,right:800,bottom:480});
});
afterEach(() => jest.restoreAllMocks());

test.each([undefined,null,NaN,Infinity,-1,'10',true])('mixed volume keeps %p unavailable rather than inventing a zero bar', missing => {
  const unknown = {...frame(1),volume:missing};
  render(<RecordedPriceChart ticker="SPY" frames={[frame(0,10),unknown,frame(2,0)]} />);
  expect(screen.getAllByTestId('volume-bar')).toHaveLength(2);
  expect(screen.getByTestId('volume-pane')).toHaveTextContent('0 shares');
  expect(screen.getByTestId('volume-pane')).toHaveTextContent('Volume unavailable for 1 of 3 visible candles');
});

test('replay excludes future premiums and future prices cannot change the displayed range', () => {
  render(plot([frame(0)],[premium(0,5),premium(1,999)]));
  expect(screen.getByTestId('contract-premium-pane')).toHaveTextContent('Range $5.00–$5.00');
  expect(screen.getAllByTestId('contract-premium')).toHaveLength(1);
});

test('a premium with no matching candle is unavailable rather than stretched onto the chart', () => {
  render(plot([frame(0)],[premium(1,999)]));
  expect(screen.queryByTestId('contract-premium-pane')).not.toBeInTheDocument();
  expect(screen.getByTestId('contract-premium-unavailable')).toHaveTextContent('visible candle window');
});

test('equivalent timezone offsets align to candle centres and missing premium times remain gaps', () => {
  render(plot([frame(0),frame(1),frame(2)],[{t:'2026-10-06T09:32:00-04:00',c:7},premium(0,5)]));
  const marks = screen.getAllByTestId('contract-premium');
  expect(marks).toHaveLength(2);
  expect(marks.every(mark => mark.tagName.toLowerCase()==='circle')).toBe(true);
  expect(Number(marks[0].getAttribute('cx'))).toBeCloseTo(12+712/6,1);
  expect(Number(marks[1].getAttribute('cx'))).toBeCloseTo(12+712*5/6,1);
  expect(screen.getByTestId('contract-premium-pane')).toHaveTextContent('2/3 visible candles matched');
});

test.each(['2026-10-06T13:30:00',null,true,'not-a-time'])('ambiguous premium timestamp %p is not aligned by position', t => {
  render(plot([frame(0)],[{t,c:5}]));
  expect(screen.queryByTestId('contract-premium-pane')).not.toBeInTheDocument();
  expect(screen.getByTestId('contract-premium-unavailable')).toBeInTheDocument();
});

test('duplicate readings at an instant remain unknown instead of choosing by array order', () => {
  render(plot([frame(0),frame(1)],[premium(0,5),{t:'2026-10-06T09:30:00-04:00',c:99},premium(1,7)]));
  expect(screen.getByTestId('contract-premium-pane')).toHaveTextContent('Range $7.00–$7.00');
  expect(screen.getByTestId('contract-premium-pane')).toHaveTextContent('1/2 visible candles matched');
});

test('numeric seconds and milliseconds align, and a measured zero premium remains known', () => {
  render(plot([frame(0),frame(1)],[{t:Date.parse(frame(1).time),c:2},{t:Date.parse(frame(0).time)/1000,c:0}]));
  expect(screen.getByTestId('contract-premium-pane')).toHaveTextContent('Range $0.00–$2.00');
  expect(screen.getByTestId('contract-premium-pane')).toHaveTextContent('2/2 visible candles matched');
});

test('panning changes premium time scope with underlying candles', () => {
  const frames = Array.from({length:100},(_,i)=>({...frame(0),time:new Date(Date.parse(frame(0).time)+i*60000).toISOString()}));
  render(plot(frames,frames.map((f,i)=>({t:f.time,c:i}))));
  expect(screen.getByTestId('contract-premium-pane')).toHaveTextContent('Range $20.00–$99.00');
  fireEvent.keyDown(screen.getByRole('region',{name:'SPY candle chart'}),{key:'Home'});
  expect(screen.getByTestId('contract-premium-pane')).toHaveTextContent('Range $0.00–$79.00');
});
