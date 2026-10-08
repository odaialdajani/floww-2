import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import RecordedPriceChart from './RecordedPriceChart';
const frames=Array.from({length:120},(_,i)=>({time:new Date(Date.UTC(2026,9,1,13,30+i*30)).toISOString(),open:100+i,high:102+i,low:99+i,close:101+i,nodes:[],duration_seconds:1800}));
beforeEach(()=>{jest.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockReturnValue({x:0,y:0,left:0,top:0,right:800,bottom:480,width:800,height:480,toJSON:()=>({})});});
afterEach(()=>jest.restoreAllMocks());
test('the candle chart displays real loaded candles and moves through earlier and later history',()=>{
 render(<RecordedPriceChart ticker="SPY" frames={frames}/>);const chart=screen.getByTestId('recorded-price-chart');fireEvent.click(screen.getByRole('button',{name:'Chart tools'}));expect(chart).toHaveAttribute('data-visible-candles','80');expect(chart).toHaveAttribute('data-window-start','40');expect(screen.getAllByTestId('price-candle')).toHaveLength(80);
 fireEvent.click(screen.getByRole('button',{name:'Earlier candles'}));expect(chart).toHaveAttribute('data-window-start','0');fireEvent.click(screen.getByRole('button',{name:'Later candles'}));expect(chart).toHaveAttribute('data-window-start','40');fireEvent.click(screen.getByRole('button',{name:'Fit history'}));expect(chart).toHaveAttribute('data-visible-candles','120');
});
test('time zoom and price zoom are independent, with a visible price-scale lock',()=>{
 render(<RecordedPriceChart ticker="SPY" frames={frames}/>);const chart=screen.getByTestId('recorded-price-chart'),lock=screen.getByRole('button',{name:'Auto scale'});
 expect(lock).toHaveAttribute('aria-pressed','true');fireEvent.click(lock);expect(lock).toHaveAttribute('aria-pressed','false');const low=chart.getAttribute('data-price-low'),high=chart.getAttribute('data-price-high');
 fireEvent.click(screen.getByRole('button',{name:'Zoom in time'}));expect(chart).toHaveAttribute('data-visible-candles','60');expect(chart).toHaveAttribute('data-price-low',low);expect(chart).toHaveAttribute('data-price-high',high);
 fireEvent.wheel(screen.getByRole('region',{name:'SPY candle chart'}),{deltaY:-100,shiftKey:true,clientX:400,clientY:220});expect(chart.getAttribute('data-price-high')).not.toBe(high);expect(chart).toHaveAttribute('data-visible-candles','60');
 fireEvent.click(lock);expect(lock).toHaveAttribute('aria-pressed','true');expect(chart.getAttribute('data-price-high')).not.toBe(high);
});
test('a stock or recorded-view change clears a held scale instead of carrying it into another reading',()=>{
 const view=render(<RecordedPriceChart ticker="SPY" frames={frames} revision="SPY:raw"/>);fireEvent.click(screen.getByRole('button',{name:'Auto scale'}));fireEvent.click(screen.getByRole('button',{name:'Zoom in time'}));
 view.rerender(<RecordedPriceChart ticker="QQQ" frames={frames.slice(0,20)} revision="QQQ:raw"/>);expect(screen.getByRole('button',{name:'Auto scale'})).toHaveAttribute('aria-pressed','true');expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-visible-candles','20');expect(screen.getByRole('region',{name:'QQQ candle chart'})).toBeVisible();
});
test('saved lines remain tied to their own earlier observation and absent lines are not rebuilt',()=>{
 const saved={...frames[0],nodes_known_at:frames[0].time,node_age_seconds:5,nodes:[{id:'gamma',level:100},{id:'vex',level:102,metric:'vex',known_at:new Date(Date.parse(frames[0].time)+1000).toISOString(),age_seconds:1}]};
 render(<RecordedPriceChart ticker="SPY" frames={[saved,frames[1]]}/>);expect(screen.getAllByTestId('saved-node-line')).toHaveLength(1);expect(screen.getByLabelText(/VEX \/ Vanna/)).toBeDisabled();expect(screen.getByText('No supported saved node lines at this candle.')).toBeVisible();
});
test('an admitted recorded zero stays distinct from unavailable VEX readings',()=>{
 const saved={...frames[0],metric_status:{vex:'zero'}};render(<RecordedPriceChart ticker="SPY" frames={[saved]} metricCoverage={{vex:{checked_candles:1,zero_candles:1}}}/>);expect(screen.getByLabelText('VEX / Vanna')).not.toBeDisabled();expect(screen.getByText(/VEX \/ Vanna was zero; no largest level stood out/)).toBeVisible();expect(screen.queryByTestId('saved-node-line')).not.toBeInTheDocument();
});
test('keyboard scrolling reaches both ends without changing the owning price data',()=>{
 render(<RecordedPriceChart ticker="SPY" frames={frames}/>);const region=screen.getByRole('region',{name:'SPY candle chart'}),chart=screen.getByTestId('recorded-price-chart');fireEvent.keyDown(region,{key:'Home'});expect(chart).toHaveAttribute('data-window-start','0');fireEvent.keyDown(region,{key:'End'});expect(chart).toHaveAttribute('data-window-start','40');expect(chart).toHaveAttribute('data-candles','120');
});

 test('each saved line title uses its own observation time',()=>{
 const row={...frames[0],nodes_known_at:'2026-10-01T13:25:00Z',node_age_seconds:300,nodes:[{id:'own-time',metric:'vex',level:101,known_at:'2026-10-01T13:29:00Z',age_seconds:60}]};
 render(<RecordedPriceChart ticker="SPY" frames={[row]}/>);
 expect(screen.getByTestId('saved-node-line').textContent).toContain('9:29 AM');
 expect(screen.getByTestId('saved-node-line').textContent).not.toContain('9:25 AM');
 });

 test('wheel zoom works when candles arrive after the chart opens',()=>{
 const {rerender}=render(<RecordedPriceChart ticker="SPY" frames={[]}/>);
 rerender(<RecordedPriceChart ticker="SPY" frames={frames}/>);
 const chart=screen.getByTestId('recorded-price-chart');
 const before=Number(chart.getAttribute('data-visible-candles'));
 fireEvent.wheel(screen.getByRole('region',{name:'SPY candle chart'}),{deltaY:-120,ctrlKey:true,clientX:250,clientY:200});
 expect(Number(chart.getAttribute('data-visible-candles'))).toBeLessThan(before);
 const high=chart.getAttribute('data-price-high');
 fireEvent.wheel(screen.getByRole('region',{name:'SPY candle chart'}),{deltaY:-120,shiftKey:true,clientX:250,clientY:200});
 expect(chart.getAttribute('data-price-high')).not.toBe(high);
 });

 test('replay prefixes grow back into the chosen history window',()=>{
 const {rerender}=render(<RecordedPriceChart ticker="SPY" frames={frames}/>);
 const chart=screen.getByTestId('recorded-price-chart');
 fireEvent.click(screen.getByRole('button',{name:'Zoom in time'}));
 expect(chart).toHaveAttribute('data-visible-candles','60');
 rerender(<RecordedPriceChart ticker="SPY" frames={frames.slice(0,1)}/>);
 expect(chart).toHaveAttribute('data-visible-candles','1');
 rerender(<RecordedPriceChart ticker="SPY" frames={frames.slice(0,20)}/>);
 expect(chart).toHaveAttribute('data-visible-candles','20');
 rerender(<RecordedPriceChart ticker="SPY" frames={frames}/>);
 expect(chart).toHaveAttribute('data-visible-candles','60');
 expect(chart).toHaveAttribute('data-window-start','60');
 });

test('image download keeps the visible candles, saved levels, colors, dates and held scale',async()=>{
 const savedFrames=frames.map((frame,index)=>index===100?{...frame,nodes_known_at:frame.time,node_age_seconds:0,nodes:[{id:'gamma',level:201}]}:frame);
 const oldCreate=URL.createObjectURL,oldRevoke=URL.revokeObjectURL;
 const create=jest.fn().mockReturnValueOnce('blob:chart-svg').mockReturnValueOnce('blob:chart-png'),revoke=jest.fn();
 URL.createObjectURL=create;URL.revokeObjectURL=revoke;
 const drawing={scale:jest.fn(),fillRect:jest.fn(),fillText:jest.fn(),drawImage:jest.fn()};
 const fills=[];Object.defineProperty(drawing,'fillStyle',{set(value){fills.push(value);}});
 jest.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue(drawing);
 jest.spyOn(HTMLCanvasElement.prototype,'toBlob').mockImplementation(callback=>callback(new Blob(['png'],{type:'image/png'})));
 jest.spyOn(window,'Image').mockImplementation(()=>{const image={};Object.defineProperty(image,'src',{set(){queueMicrotask(()=>image.onload());}});return image;});
 const click=jest.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 try{
  render(<RecordedPriceChart ticker="SPY" frames={savedFrames}/>);
  fireEvent.click(screen.getByRole('button',{name:'Zoom in time'}));fireEvent.click(screen.getByRole('button',{name:'Auto scale'}));
  const chart=screen.getByTestId('recorded-price-chart'),before={start:chart.getAttribute('data-window-start'),count:chart.getAttribute('data-visible-candles'),low:chart.getAttribute('data-price-low'),high:chart.getAttribute('data-price-high')};
  // These are the styles resolved by the browser from the chart stylesheet.
  chart.querySelector('.recorded-candle-up').style.color='#57c5b0';chart.querySelector('.recorded-price-label').style.fill='#aebcc9';
  chart.querySelector('.recorded-chart-surface').style.backgroundColor='#111111';
  fireEvent.click(screen.getByRole('button',{name:'Chart tools'}));
  await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Download chart image'})));
  await waitFor(()=>expect(click).toHaveBeenCalledTimes(1));
  const svgBlob=create.mock.calls[0][0],xml=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsText(svgBlob);});
  expect(svgBlob.type).toContain('image/svg+xml');expect(xml.match(/data-testid="price-candle"/g)).toHaveLength(60);expect(xml).toContain('data-testid="saved-node-line"');expect(xml).toContain('color: rgb(87, 197, 176)');expect(xml).toContain('fill: #aebcc9');expect(xml).toContain('New York');
  expect(drawing.fillText.mock.calls[0][0]).toContain('SPY |');expect(drawing.fillText.mock.calls[0][0]).toContain('New York');expect(drawing.drawImage).toHaveBeenCalledWith(expect.anything(),0,42,800,480);
  expect(fills[0]).toBe('rgb(17, 17, 17)');
  expect(create.mock.calls[1][0].type).toBe('image/png');expect(click.mock.instances[0].download).toBe('SPY-price-chart.png');expect(click.mock.instances[0].href).toBe('blob:chart-png');expect(revoke).toHaveBeenCalledWith('blob:chart-svg');
  expect(chart).toHaveAttribute('data-window-start',before.start);expect(chart).toHaveAttribute('data-visible-candles',before.count);expect(chart).toHaveAttribute('data-price-low',before.low);expect(chart).toHaveAttribute('data-price-high',before.high);expect(screen.getByRole('button',{name:'Auto scale'})).toHaveAttribute('aria-pressed','false');
  await new Promise(resolve=>setTimeout(resolve,1100));expect(revoke).toHaveBeenCalledWith('blob:chart-png');
 }finally{URL.createObjectURL=oldCreate;URL.revokeObjectURL=oldRevoke;}
});
test('an unavailable image download reports the failure without changing the chart',async()=>{
 jest.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue(null);
 render(<RecordedPriceChart ticker="SPY" frames={frames}/>);fireEvent.click(screen.getByRole('button',{name:'Chart tools'}));
 await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Download chart image'})));
 expect(screen.getByRole('alert')).toHaveTextContent('Chart image could not be saved. Try again.');expect(screen.getByTestId('recorded-price-chart')).toHaveAttribute('data-visible-candles','80');expect(screen.getByRole('button',{name:'Download chart image'})).not.toBeDisabled();
});
