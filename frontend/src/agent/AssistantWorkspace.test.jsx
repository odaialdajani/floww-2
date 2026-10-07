import React from 'react';
import {act,render,screen,fireEvent,waitFor,within} from '@testing-library/react';
import AgentProvider,{useAgent} from './AgentProvider';
import AgentPanel from './AgentPanel';
import AgentCommandBar from './AgentCommandBar';
import {publishScreenContext} from './useScreenContext';
import AskLodestar from '../components/heatseeker/AskLodestar';

const models=[{id:'first',label:'First model',efforts:['low','medium','high'],default_effort:'medium',speeds:['default','priority']}];
const selected={model:'first',effort:'medium',speed:'default'};
const catalog=()=>({ok:true,json:async()=>({models,selected,usage:{calls:2,daily_limit:40}})});
function Workspace(){
 const a=useAgent();const [chartClicks,setChartClicks]=React.useState(0);
 return <><button onClick={()=>setChartClicks(n=>n+1)}>Chart control</button><output data-testid="chart-clicks">{chartClicks}</output><button onClick={()=>a.askQuestion('From another entry')}>Ask from chart</button><button onClick={()=>{for(let i=0;i<20;i++)a.pushTurn({turn_id:'thread-'+i,ticker:'SPY',question:'Actual stored question '+i,status:'completed',text:'Answer '+i+' '+'.'.repeat(500)},a.context);}}>Seed saved thread</button><AskLodestar/><AgentCommandBar/><AgentPanel/></>;
}
beforeAll(()=>Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true}));
beforeEach(()=>{
 publishScreenContext({ticker:'SPY',page:'heatseeker',displayMode:'live',overlayMetric:'raw'});
 global.fetch=jest.fn(async url=>String(url).endsWith('/session')?{ok:true}
  :String(url).endsWith('/models')?catalog()
  :String(url).endsWith('/ask')?{ok:true,json:async()=>({turn_id:'asked'})}
  :{ok:true,json:async()=>({turn_id:'asked',ticker:'SPY',question:'Uncertain draft',status:'completed',text:'Actual saved answer'})});
});
function renderWorkspace(){return render(<AgentProvider><Workspace/></AgentProvider>);}
function openChat(){fireEvent.click(screen.getByRole('button',{name:'Open Ask FLOWW'}));return screen.getByRole('region',{name:'Ask FLOWW chat'});}
async function openSettings(){fireEvent.click(screen.getByRole('button',{name:'Ask FLOWW settings'}));return screen.findByRole('dialog',{name:'Ask FLOWW settings'});}

test('opening chat keeps chart access and makes no model request until the gear is used',async()=>{
 renderWorkspace();expect(global.fetch).not.toHaveBeenCalled();
 const chat=openChat();expect(chat).not.toHaveAttribute('aria-modal');
 expect(screen.queryByRole('button',{name:/AI choices/})).toBeNull();expect(global.fetch).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText('Chart control'));expect(screen.getByTestId('chart-clicks')).toHaveTextContent('1');
 await openSettings();await screen.findByLabelText('Model');
 expect(global.fetch.mock.calls.map(([url])=>String(url).split('/').pop())).toEqual(['session','models']);
 expect(screen.getByText(/2 of 40 app calls/)).toBeInTheDocument();
 expect(screen.getByText('Chart control').closest('[inert]')).not.toBeNull();
 const close=screen.getByRole('button',{name:'Close settings'});expect(close).toHaveFocus();
 const end=screen.getByRole('button',{name:'End research session'});
 fireEvent.keyDown(close,{key:'Tab',shiftKey:true});expect(end).toHaveFocus();
 fireEvent.keyDown(end,{key:'Tab'});expect(close).toHaveFocus();
 screen.getByText('Chart control').focus();expect(close).toHaveFocus();
 fireEvent.keyDown(screen.getByLabelText('Model'),{key:'Escape'});
 expect(screen.queryByRole('dialog',{name:'Ask FLOWW settings'})).toBeNull();
 expect(screen.getByRole('region',{name:'Ask FLOWW chat'})).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Ask FLOWW settings'})).toHaveFocus();
 expect(screen.getByText('Chart control').closest('[inert]')).toBeNull();
});

test('pending choices and unsent questions survive settings and chat close without enabling another entry',async()=>{
 let releaseModels;global.fetch.mockImplementation(async url=>String(url).endsWith('/session')?{ok:true}:new Promise(resolve=>{releaseModels=resolve;}));
 renderWorkspace();openChat();fireEvent.change(screen.getByRole('textbox'),{target:{value:'Keep this draft'}});
 await openSettings();await waitFor(()=>expect(releaseModels).toBeDefined());
 const originalChecking=screen.getByRole('button',{name:'Checking AI choices…'});
 fireEvent.click(screen.getByRole('button',{name:'Close settings'}));fireEvent.click(screen.getByRole('button',{name:'Close Ask FLOWW'}));
 expect(global.fetch).toHaveBeenCalledTimes(2);
 openChat();expect(screen.getByRole('textbox')).toHaveValue('Keep this draft');expect(screen.getByRole('button',{name:'Ask',exact:true})).toBeDisabled();
 fireEvent.click(screen.getByText('Ask from chart'));
 expect(global.fetch).toHaveBeenCalledTimes(2);expect(screen.getByRole('alert')).toHaveTextContent('Confirm your AI choice');
 await openSettings();expect(screen.getByRole('button',{name:'Checking AI choices…'})).toBe(originalChecking);expect(global.fetch).toHaveBeenCalledTimes(2);
 await act(async()=>releaseModels(catalog()));await screen.findByLabelText('Model');
 fireEvent.click(screen.getByRole('button',{name:'Close settings'}));expect(screen.getByRole('button',{name:'Ask',exact:true})).not.toBeDisabled();
});

test('an uncertain save remains blocked after close and reopening until explicit reload confirms choices',async()=>{
 global.fetch.mockImplementation(async url=>String(url).endsWith('/prefs')?{ok:false}:String(url).endsWith('/session')?{ok:true}:catalog());
 renderWorkspace();openChat();fireEvent.change(screen.getByRole('textbox'),{target:{value:'Uncertain draft'}});
 await openSettings();await screen.findByLabelText('Thinking depth');
 fireEvent.change(screen.getByLabelText('Thinking depth'),{target:{value:'low'}});
 fireEvent.click(screen.getByRole('button',{name:'Save AI choice'}));await screen.findByText(/choice was not confirmed/);
 fireEvent.click(screen.getByRole('button',{name:'Close settings'}));fireEvent.click(screen.getByRole('button',{name:'Close Ask FLOWW'}));
 openChat();expect(screen.getByRole('textbox')).toHaveValue('Uncertain draft');expect(screen.getByRole('button',{name:'Ask',exact:true})).toBeDisabled();
 const before=global.fetch.mock.calls.length;
 fireEvent.click(screen.getByText('Ask from chart'));
 fireEvent.click(screen.getByTestId('ask-lodestar-btn'));fireEvent.click(screen.getByTestId('ask-lodestar-q-0'));
 expect(global.fetch).toHaveBeenCalledTimes(before);expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'))).toHaveLength(0);
 await openSettings();expect(screen.getByLabelText('Thinking depth')).toHaveValue('low');expect(screen.getByText(/choice was not confirmed/)).toBeInTheDocument();expect(global.fetch).toHaveBeenCalledTimes(before);
 fireEvent.click(screen.getByRole('button',{name:'Reload choices'}));await waitFor(()=>expect(screen.getByLabelText('Thinking depth')).toHaveValue('medium'));
 fireEvent.click(screen.getByRole('button',{name:'Close settings'}));expect(screen.getByRole('button',{name:'Ask',exact:true})).not.toBeDisabled();
});

test('the thread shows stored questions and keeps only one full answer body mounted above the composer',()=>{
 renderWorkspace();const chat=openChat();fireEvent.click(screen.getByText('Seed saved thread'));
 const scope=within(chat);expect(scope.getByText('Actual stored question 0')).toBeInTheDocument();expect(scope.getByText('Actual stored question 19')).toBeInTheDocument();
 expect(scope.getAllByRole('article',{name:/Research answer/})).toHaveLength(1);
 expect(scope.getAllByRole('button',{name:'Open full answer'})).toHaveLength(19);
 fireEvent.click(scope.getAllByRole('button',{name:'Open full answer'})[0]);expect(scope.getAllByRole('article',{name:/Research answer/})).toHaveLength(1);
 expect(scope.getByRole('article',{name:/Research answer/})).toHaveTextContent('Answer 0');
 const thread=chat.querySelector('.assistant-thread'),composer=chat.querySelector('.assistant-composer');
 expect(thread.compareDocumentPosition(composer)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
 expect(chat.querySelectorAll('.assistant-turn')).toHaveLength(20);
});

test('session end clears private drafts and shared choice guard while discarding a late choices response',async()=>{
 let releaseModels;global.fetch.mockImplementation(async url=>String(url).endsWith('/session')?{ok:true}:new Promise(resolve=>{releaseModels=resolve;}));
 renderWorkspace();openChat();fireEvent.change(screen.getByRole('textbox'),{target:{value:'Private pending question'}});
 await openSettings();await waitFor(()=>expect(releaseModels).toBeDefined());
 act(()=>window.dispatchEvent(new Event('floww-research-session-ended')));
 expect(screen.queryByRole('dialog',{name:'Ask FLOWW settings'})).toBeNull();expect(screen.getByRole('textbox')).toHaveValue('');
 await act(async()=>releaseModels(catalog()));
 expect(screen.queryByLabelText('Model')).toBeNull();expect(screen.queryByText('Confirm your AI choice in settings before asking.')).toBeNull();
 expect(screen.getByText(/Research session ended/)).toBeInTheDocument();
});

test('first gear use loads choices once after strict lifecycle checks and remains usable',async()=>{
 render(<React.StrictMode><AgentProvider><Workspace/></AgentProvider></React.StrictMode>);
 openChat();await openSettings();await screen.findByLabelText('Model');
 expect(screen.getByLabelText('Model')).toHaveValue('first');
 expect(screen.getByRole('button',{name:'Reload choices'})).not.toBeDisabled();
 expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/models'))).toHaveLength(1);
});

test('shortcut close leaves focus on the chart control the user already chose',()=>{
 renderWorkspace();const opener=screen.getByRole('button',{name:'Open Ask FLOWW'});opener.focus();openChat();
 const chart=screen.getByText('Chart control');chart.focus();
 fireEvent.keyDown(window,{key:'k',ctrlKey:true});
 expect(screen.queryByRole('region',{name:'Ask FLOWW chat'})).toBeNull();expect(chart).toHaveFocus();
});

test('closing the gear before first-use loading starts cancels its hidden timer',async()=>{
 jest.useFakeTimers();const view=renderWorkspace();
 try{
  openChat();fireEvent.click(screen.getByRole('button',{name:'Ask FLOWW settings'}));
  fireEvent.click(screen.getByRole('button',{name:'Close settings'}));
  await act(async()=>jest.advanceTimersByTime(1));
  expect(global.fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Ask FLOWW settings'}));
  await act(async()=>jest.advanceTimersByTime(1));
  expect(screen.getByLabelText('Model')).toHaveValue('first');
  expect(global.fetch.mock.calls.map(([url])=>String(url).split('/').pop())).toEqual(['session','models']);
 }finally{view.unmount();jest.useRealTimers();}
});

test('closing a gear opened during research cannot load hidden choices when research finishes',async()=>{
 jest.useFakeTimers();let admit;const view=renderWorkspace();
 global.fetch.mockImplementation(async url=>String(url).endsWith('/session')?{ok:true}
  :String(url).endsWith('/ask')?new Promise(resolve=>{admit=resolve;})
  :String(url).endsWith('/models')?catalog()
  :{ok:true,json:async()=>({turn_id:'busy-answer',ticker:'SPY',question:'Work first',status:'completed',text:'Finished active research'})});
 try{
  openChat();fireEvent.change(screen.getByRole('textbox'),{target:{value:'Work first'}});
  fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));await waitFor(()=>expect(admit).toBeDefined());
  fireEvent.click(screen.getByRole('button',{name:'Ask FLOWW settings'}));fireEvent.click(screen.getByRole('button',{name:'Close settings'}));
  await act(async()=>admit({ok:true,json:async()=>({turn_id:'busy-answer'})}));
  await act(async()=>jest.advanceTimersByTime(1));
  expect(screen.getByText('Finished active research')).toBeInTheDocument();
  expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/models'))).toHaveLength(0);
  expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/session'))).toHaveLength(1);
 }finally{view.unmount();jest.useRealTimers();}
});

test('an explicitly confirmed resave resolves uncertainty even when a later choices reload fails',async()=>{
 let writes=0,failReload=false;
 global.fetch.mockImplementation(async(url,opts)=>String(url).endsWith('/prefs')?{ok:++writes>1}
  :String(url).endsWith('/session')?{ok:true}
  :failReload?{ok:false,json:async()=>({error:'Temporary choices outage'})}:catalog());
 renderWorkspace();openChat();fireEvent.change(screen.getByRole('textbox'),{target:{value:'Continue with my confirmed choice'}});
 await openSettings();await screen.findByLabelText('Thinking depth');
 fireEvent.change(screen.getByLabelText('Thinking depth'),{target:{value:'low'}});
 fireEvent.click(screen.getByRole('button',{name:'Save AI choice'}));await screen.findByText(/choice was not confirmed/);
 fireEvent.click(screen.getByRole('button',{name:'Save AI choice'}));await screen.findByText('Saved for your next question.');
 failReload=true;fireEvent.click(screen.getByRole('button',{name:'Reload choices'}));await screen.findByText('AI choices could not be checked. Reload choices to try again.');
 fireEvent.click(screen.getByRole('button',{name:'Close settings'}));
 expect(screen.getByRole('button',{name:'Ask',exact:true})).not.toBeDisabled();
 expect(screen.queryByText('Confirm your AI choice in settings before asking.')).toBeNull();
 expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/prefs'))).toHaveLength(2);
 expect(global.fetch.mock.calls.filter(([url])=>String(url).endsWith('/ask'))).toHaveLength(0);
});
