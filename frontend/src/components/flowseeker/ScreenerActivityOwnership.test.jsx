
import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import FlowseekerProBlademap from './FlowseekerProBlademap';
jest.mock('./MarketCoverage',()=>()=>null);
jest.mock('./ContractReview',()=>()=>null);
jest.mock('../heatseeker/useTickerDirectory',()=>{const tickers={popular:['SPY','NVDA']};return ()=>({tickers,status:'complete',retry:jest.fn()});});
const response=data=>({ok:true,status:200,json:async()=>data});
beforeEach(()=>localStorage.clear());
const chooseNvda=()=>{const picker=screen.getByRole('combobox',{name:'Focused ticker'});fireEvent.change(picker,{target:{value:'NVDA'}});fireEvent.keyDown(picker,{key:'Enter'});};

test('changing focus clears the previous stock activity reading while the new request is pending',async()=>{
 let nextReading;
 global.fetch=jest.fn(async url=>String(url).includes('/vpin/SPY')?response({vpin:0.321}):String(url).includes('/vpin/NVDA')?new Promise(resolve=>{nextReading=resolve;}):response({rows:[]}));
 render(<FlowseekerProBlademap active/>);
 expect(await screen.findByText('VPIN 0.321')).toBeInTheDocument();
 chooseNvda();await waitFor(()=>expect(nextReading).toBeDefined());
 expect(screen.getByRole('heading',{name:'Stock details · NVDA'})).toBeInTheDocument();
 expect(screen.queryByText('VPIN 0.321')).not.toBeInTheDocument();
 expect(screen.getByText('VPIN — no feed')).toBeInTheDocument();
 await act(async()=>nextReading(response({vpin:null})));
 expect(screen.getByText('VPIN — no feed')).toBeInTheDocument();
 expect(screen.queryByText('VPIN 0.000')).not.toBeInTheDocument();
});

test('a delayed old stock response cannot replace the new stock activity reading',async()=>{
 let previousReading;
 global.fetch=jest.fn(async url=>String(url).includes('/vpin/SPY')?new Promise(resolve=>{previousReading=resolve;}):String(url).includes('/vpin/NVDA')?response({vpin:0.654}):response({rows:[]}));
 render(<FlowseekerProBlademap active/>);await waitFor(()=>expect(previousReading).toBeDefined());
 const previousSignal=global.fetch.mock.calls.find(([url])=>String(url).includes('/vpin/SPY'))[1].signal;
 chooseNvda();expect(await screen.findByText('VPIN 0.654')).toBeInTheDocument();expect(previousSignal.aborted).toBe(true);
 await act(async()=>previousReading(response({vpin:0.321})));
 expect(screen.getByText('VPIN 0.654')).toBeInTheDocument();expect(screen.queryByText('VPIN 0.321')).not.toBeInTheDocument();
});


test.each([
 ['empty text',{vpin:''}], ['boolean',{vpin:false}], ['list',{vpin:[]}], ['object',{vpin:{}}],
 ['unsupported numeric text',{vpin:'0.3'}], ['explicitly unavailable',{vpin:.3,status:'unavailable'}],
])('unusable focused activity %s never becomes zero or a usable reading',async(_label,body)=>{
 global.fetch=jest.fn(async url=>String(url).includes('/api/vpin/')?response(body):response({rows:[]}));
 await act(async()=>render(<FlowseekerProBlademap active/>));
 expect(screen.getByText('VPIN — no feed')).toBeInTheDocument();
 expect(screen.queryByText('VPIN 0.000')).not.toBeInTheDocument();expect(screen.queryByText('VPIN 0.300')).not.toBeInTheDocument();expect(screen.queryByText('VPIN NaN')).not.toBeInTheDocument();
});

test('a real numeric zero remains available rather than becoming missing',async()=>{
 global.fetch=jest.fn(async url=>String(url).includes('/api/vpin/')?response({vpin:0}):response({rows:[]}));
 await act(async()=>render(<FlowseekerProBlademap active/>));
 expect(screen.getByText('VPIN 0.000')).toBeInTheDocument();expect(screen.queryByText('VPIN — no feed')).not.toBeInTheDocument();
});


test.each([0,.3])('the real nested engine reading %s is shown only after actual observations, with time unknown',async(value)=>{
 global.fetch=jest.fn(async url=>String(url).includes('/api/vpin/')?response({current:{vpin:value},history:{vpin_history_length:3},buckets:{finalized_count:3}}):response({rows:[]}));
 await act(async()=>render(<FlowseekerProBlademap active/>));
 expect(screen.getByText('VPIN '+value.toFixed(3))).toHaveAttribute('title','Source observation time unknown');
});

test.each([
 ['cold default',{current:{vpin:0},history:{vpin_history_length:0}}],
 ['missing history',{current:{vpin:.3}}],
 ['text history count',{current:{vpin:.3},history:{vpin_history_length:'3'}}],
 ['fractional history count',{current:{vpin:.3},history:{vpin_history_length:1.5}}],
 ['false nested reading',{current:{vpin:false},history:{vpin_history_length:3}}],
 ['array nested reading',{current:{vpin:[]},history:{vpin_history_length:3}}],
 ['text nested reading',{current:{vpin:'0.3'},history:{vpin_history_length:3}}],
 ['explicit nested unavailable',{current:{vpin:.3},history:{vpin_history_length:3},status:'unavailable'}],
 ['explicit nested unavailable flag',{current:{vpin:.3},history:{vpin_history_length:3},available:false}],
 ['explicit legacy unavailable flag',{vpin:.3,available:false}],
])('the engine %s is not a usable activity reading',async(_label,body)=>{
 global.fetch=jest.fn(async url=>String(url).includes('/api/vpin/')?response(body):response({rows:[]}));
 await act(async()=>render(<FlowseekerProBlademap active/>));
 expect(screen.getByText('VPIN — no feed')).toBeInTheDocument();expect(screen.queryByText('VPIN 0.000')).not.toBeInTheDocument();expect(screen.queryByText('VPIN 0.300')).not.toBeInTheDocument();
});

test('the focused engine uses the actual ticker route with the focus safely encoded',async()=>{
 localStorage.setItem('th-prefs-v1',JSON.stringify({focusTicker:'^SPX'}));
 global.fetch=jest.fn(async url=>String(url).includes('/api/vpin/')?response({vpin:.3}):response({rows:[]}));
 await act(async()=>render(<FlowseekerProBlademap active/>));
 expect(global.fetch.mock.calls.some(([url])=>String(url).endsWith('/api/vpin/%5ESPX'))).toBe(true);
 expect(global.fetch.mock.calls.some(([url])=>String(url).includes('/api/vpin?'))).toBe(false);
});
