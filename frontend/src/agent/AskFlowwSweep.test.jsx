import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import AgentPanelAnswer from './AgentPanelAnswer';
import AgentProvider,{useAgent} from './AgentProvider';
import AgentConversation from './AgentConversation';
import {publishScreenContext} from './useScreenContext';
import {requestFailureText} from './requestFailure';
jest.mock('./AgentModelSettings',()=>()=>null);
beforeAll(()=>Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true}));
beforeEach(()=>{publishScreenContext({ticker:'SPY',dte:'all'});global.fetch=jest.fn();});
test('an older section without fact references keeps its answer readable',()=>{
 render(<AgentPanelAnswer turn={{turn_id:'legacy',ticker:'SPY',status:'completed',answer:{summary:'Saved useful reading',model_sections:[{name:'Verdict',text:'Evidence limited'}]}}}/>);
 expect(screen.getByText('Saved useful reading')).toBeVisible();
 expect(screen.getByText(/Source references are unavailable for this saved section/)).toBeVisible();
});
function Seed(){const a=useAgent();return <button onClick={()=>a.pushTurn({turn_id:'saved-spy',ticker:'SPY',status:'completed',question:'Saved SPY question',text:'Saved SPY answer'})}>Seed saved answer</button>;}
test('a follow-up cannot silently switch from a saved answer to another stock',()=>{
 render(<AgentProvider><Seed/><AgentConversation/></AgentProvider>);
 fireEvent.click(screen.getByText('Seed saved answer'));
 act(()=>publishScreenContext({ticker:'QQQ',dte:'all'}));
 expect(screen.queryByRole('button',{name:'Explain the uncertainty'})).not.toBeInTheDocument();
 expect(screen.getByText('Select SPY to ask a follow-up about this answer.')).toBeVisible();
 expect(global.fetch).not.toHaveBeenCalled();
});
test('matching-stock follow-ups remain manual and focus the draft',()=>{
 render(<AgentProvider><Seed/><AgentConversation/></AgentProvider>);
 fireEvent.click(screen.getByText('Seed saved answer'));
 fireEvent.click(screen.getByRole('button',{name:'Explain the uncertainty'}));
 expect(screen.getByRole('textbox').value).toContain('For SPY');
 expect(screen.getByRole('textbox')).toHaveFocus();
 expect(global.fetch).not.toHaveBeenCalled();
});

test('missing saved facts do not crash a section with old references',()=>{
 render(<AgentPanelAnswer turn={{ticker:'SPY',status:'completed',answer:{summary:'Known saved summary',model_sections:[{name:'Verdict',text:'Saved interpretation',fact_ids:['lost-reference']}]}}}/>);
 expect(screen.getByText('Known saved summary')).toBeVisible();
 expect(screen.getByText(/Source references are unavailable for this saved section/)).toBeVisible();
});

test.each([{facts:{}},{facts:[null]},{model_sections:[null]},{snapshots:{}},{snapshots:[null]}])('malformed saved collections preserve the readable summary: %j',partial=>{
 render(<AgentPanelAnswer turn={{ticker:'SPY',status:'completed',answer:{summary:'Preserved summary',...partial}}}/>);
 expect(screen.getByText('Preserved summary')).toBeVisible();
 expect(screen.getByText(/Some saved answer details are incomplete/)).toBeVisible();
});
test('empty legacy references cannot claim a checked assessment',()=>{
 render(<AgentPanelAnswer turn={{ticker:'SPY',status:'completed',answer:{summary:'Saved summary',mode:'model-assisted',model_status:'Checked interpretation',model_sections:[{name:'Verdict',text:'An earlier interpretation',fact_ids:[]}]}}}/>);
 expect(screen.getByText(/Source references are unavailable for this saved section/)).toBeVisible();
 expect(screen.queryByText('AI explanation checked')).not.toBeInTheDocument();
 expect(screen.queryByRole('region',{name:'Checked assessment'})).not.toBeInTheDocument();
});

function SeedMalformed(){const a=useAgent();return <button onClick={()=>{a.pushTurn({turn_id:'bad-old',ticker:'SPY',status:'completed',question:'Old question',answer:{summary:{old:'invalid'}}});a.pushTurn({turn_id:'good-new',ticker:'SPY',status:'completed',question:'New question',text:'New valid answer'});}}>Seed old malformed preview</button>;}
test('an incomplete older preview cannot crash the readable current answer',()=>{
 render(<AgentProvider><SeedMalformed/><AgentConversation/></AgentProvider>);
 fireEvent.click(screen.getByText('Seed old malformed preview'));
 expect(screen.getByText('New valid answer')).toBeVisible();
 expect(screen.getByText('Saved answer preview is unavailable.')).toBeVisible();
});

function SeedNavigation(){const a=useAgent();return <button onClick={()=>a.pushTurn({turn_id:'local-nav',localOnly:true,ticker:'SPY',status:'completed',question:'Open chart',text:'Opened chart.'})}>Seed local navigation</button>;}
test('a local navigation reply has no market follow-up or selection warning',()=>{
 render(<AgentProvider><SeedNavigation/><AgentConversation/></AgentProvider>);
 fireEvent.click(screen.getByText('Seed local navigation'));
 expect(screen.getByText('Opened chart.')).toBeVisible();
 expect(screen.queryByText(/to ask a follow-up about this answer/)).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Explain the uncertainty'})).not.toBeInTheDocument();
});

test('the current server validation message survives the actual chat request path',async()=>{
 const error='Specific dated or timed history comparisons are unavailable; use the previous saved observation';
 global.fetch=jest.fn(async url=>String(url).endsWith('/session')?{ok:true}:{ok:false,status:422,json:async()=>({error,status_code:422,path:'/api/agent/ask'})});
 render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Show SPY change since 2026-10-01'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent(error));
 expect(screen.getByRole('textbox')).toHaveValue('Show SPY change since 2026-10-01');
});
test.each([403,503])('other failures stay generic for status %s',status=>{
 expect(requestFailureText(status,{error:'private transport detail'})).toBe('Research request could not start');
});
test('oversized validation messages remain bounded',()=>{
 expect(requestFailureText(422,{error:'x'.repeat(501)})).toBe('Research request could not start');
});

function SeedDamagedRunning(){const a=useAgent();return <button onClick={()=>a.pushTurn({turn_id:'stored-running',status:'running',question:{damaged:true},ticker:{damaged:true},progress:{damaged:true}})}>Seed damaged unfinished question</button>;}
test('damaged saved text stays readable when checking the same unfinished question',async()=>{
 global.fetch=jest.fn(()=>new Promise(()=>{}));
 render(<AgentProvider><SeedDamagedRunning/><AgentConversation/></AgentProvider>);
 fireEvent.click(screen.getByText('Seed damaged unfinished question'));
 fireEvent.click(screen.getByRole('button',{name:'Check progress'}));
 await waitFor(()=>expect(screen.getByRole('region',{name:'Question in progress'})).toBeVisible());
 expect(screen.getByRole('region',{name:'Question in progress'})).toHaveTextContent('The saved question is unavailable.');
 expect(screen.getByRole('region',{name:'Question in progress'})).toHaveTextContent('Stock unavailable');
 expect(global.fetch.mock.calls.every(([url])=>!String(url).endsWith('/ask'))).toBe(true);
});
test('an incomplete local navigation reply cannot crash the answer display',()=>{
 render(<AgentPanelAnswer turn={{localOnly:true,text:{damaged:true}}}/>);
 expect(screen.getByText('Navigation details are unavailable.')).toBeVisible();
});

test('a damaged saved chart-action list cannot hide the market summary',()=>{
 render(<AgentPanelAnswer turn={{ticker:null,status:'completed',answer:{scope:'market',summary:'Saved market summary',actions:{damaged:true}}}}/>);
 expect(screen.getByText('Saved market summary')).toBeVisible();
 expect(screen.getByText(/Some saved answer details are incomplete/)).toBeVisible();
});
