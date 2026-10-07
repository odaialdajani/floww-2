import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import AgentProvider from './AgentProvider';
import AgentConversation from './AgentConversation';
import {publishScreenContext} from './useScreenContext';

jest.mock('./AgentModelSettings',()=>()=>null);
beforeAll(()=>Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true}));

test('a previous-selection answer is visibly historical in the real conversation',async()=>{
 publishScreenContext({ticker:'SPY',snapshotId:'stored-one'});
 global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).endsWith('/session')?{}:String(url).endsWith('/ask')?{turn_id:'one'}:{turn_id:'one',status:'completed',ticker:'SPY',text:'Owning observation answer'}}));
 render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Review this wall'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(screen.getByText('Owning observation answer')).toBeInTheDocument());
 const {act}=require('@testing-library/react');
 act(()=>publishScreenContext({ticker:'SPY',snapshotId:'stored-two'}));
 expect(screen.getByText(/selection saved when you asked.*different or newer reading/)).toBeInTheDocument();
 expect(screen.getByText('Owning observation answer')).toBeInTheDocument();
});

test.each([
 'Choose at most three valid tickers',
 '<img src=x onerror="unsafe()"> Choose one explicit expiry scope per question',
])('the real conversation shows rejected-request text safely: %s',async detail=>{
 publishScreenContext({ticker:'SPY',dte:'all',displayMode:'live',overlayMetric:'raw'});
 global.fetch=jest.fn(async url=>String(url).endsWith('/session')?{ok:true,json:async()=>({})}:{ok:false,status:422,json:async()=>({detail})});
 const {container}=render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Compare the selected markets'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(screen.getByRole('alert').textContent).toBe(detail));
 expect(container.querySelector('img,script')).toBeNull();
 expect(screen.queryByRole('status')).toBeNull();
 expect(screen.queryByLabelText(/Research answer/)).toBeNull();
 expect(global.fetch).toHaveBeenCalledTimes(2);
});

function ConversationToggle(){const [shown,setShown]=require('react').useState(true);return <><button onClick={()=>setShown(!shown)}>Toggle chat</button>{shown && <AgentConversation/>}</>;}

test('an unsent question survives closing and reopening the chat',()=>{
 publishScreenContext({ticker:'SPY'});
 render(<AgentProvider><ConversationToggle/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Keep this unsent question'}});
 fireEvent.click(screen.getByText('Toggle chat'));fireEvent.click(screen.getByText('Toggle chat'));
 expect(screen.getByRole('textbox')).toHaveValue('Keep this unsent question');
});

test('a locally blocked question keeps the draft without starting research',async()=>{
 publishScreenContext({ticker:null});global.fetch=jest.fn();
 render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Choose a market first'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent("Choose a ticker in Screener, Options map or Unusual flow before asking."));
 expect(screen.getByRole('textbox')).toHaveValue('Choose a market first');
 expect(global.fetch).not.toHaveBeenCalled();
});

test('a rejected question keeps the draft for correction',async()=>{
 publishScreenContext({ticker:'SPY'});
 global.fetch=jest.fn(async url=>String(url).endsWith('/session')?{ok:true,json:async()=>({})}:{ok:false,status:422,json:async()=>({detail:'Choose one expiry'})});
 render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Compare my selections'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('Choose one expiry'));
 expect(screen.getByRole('textbox')).toHaveValue('Compare my selections');
 expect(global.fetch).toHaveBeenCalledTimes(2);
});

test('late admission clears only the submitted draft, never newer typing',async()=>{
 publishScreenContext({ticker:'SPY'});let release;
 global.fetch=jest.fn(async url=>String(url).endsWith('/session')?{ok:true,json:async()=>({})}:String(url).endsWith('/ask')?await new Promise(resolve=>{release=resolve;}):{ok:true,json:async()=>({turn_id:'accepted',status:'completed',text:'Completed answer'})});
 render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'First question'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(release).toBeDefined());
 expect(screen.getByRole('textbox')).toHaveValue('First question');
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Second draft'}});
 const {act}=require('@testing-library/react');
 await act(async()=>release({ok:true,json:async()=>({turn_id:'accepted'})}));
 await waitFor(()=>expect(screen.getByText('Completed answer')).toBeInTheDocument());
 expect(screen.getByRole('textbox')).toHaveValue('Second draft');
});

test('accepted admission clears the unchanged submitted draft',async()=>{
 publishScreenContext({ticker:'SPY'});
 global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).endsWith('/session')?{}:String(url).endsWith('/ask')?{turn_id:'accepted'}:{turn_id:'accepted',status:'completed',text:'Accepted answer'}}));
 render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Accepted question'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(screen.getByText('Accepted answer')).toBeInTheDocument());
 expect(screen.getByRole('textbox')).toHaveValue('');
});


test('editing away and back to the same text creates a new draft that late admission keeps',async()=>{
 publishScreenContext({ticker:'SPY'});let release;
 global.fetch=jest.fn(async url=>String(url).endsWith('/session')?{ok:true,json:async()=>({})}:String(url).endsWith('/ask')?await new Promise(resolve=>{release=resolve;}):{ok:true,json:async()=>({turn_id:'accepted',status:'completed',text:'Same text answer'})});
 render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Repeat question'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(release).toBeDefined());
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Different draft'}});
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Repeat question'}});
 const {act}=require('@testing-library/react');
 await act(async()=>release({ok:true,json:async()=>({turn_id:'accepted'})}));
 await waitFor(()=>expect(screen.getByText('Same text answer')).toBeInTheDocument());
 expect(screen.getByRole('textbox')).toHaveValue('Repeat question');
});

test('ending the session clears the unsent private question on reopening',async()=>{
 publishScreenContext({ticker:'SPY'});
 global.fetch=jest.fn(async()=>({ok:true,json:async()=>({status:'signed-out'})}));
 render(<AgentProvider><ConversationToggle/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Private unsent question'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask FLOWW settings'}));
 fireEvent.click(screen.getByRole('button',{name:'End research session'}));
 await waitFor(()=>expect(screen.getByText(/Research session ended/)).toBeInTheDocument());
 fireEvent.click(screen.getByText('Toggle chat'));fireEvent.click(screen.getByText('Toggle chat'));
 expect(screen.getByRole('textbox')).toHaveValue('');
});

test('starter questions fill the draft without starting a request',()=>{
 publishScreenContext({ticker:'SPY'});global.fetch=jest.fn();
 render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.click(screen.getByRole('button',{name:'What is missing?',exact:true}));
 expect(screen.getByRole('textbox').value).toContain('selected SPY data');
 expect(global.fetch).not.toHaveBeenCalled();
});

test('Enter submits a question while Shift Enter keeps editing',async()=>{
 publishScreenContext({ticker:'SPY'});
 global.fetch=jest.fn(async url=>({ok:true,json:async()=>String(url).endsWith('/session')?{}:String(url).endsWith('/ask')?{turn_id:'keyboard'}:{turn_id:'keyboard',ticker:'SPY',status:'completed',text:'Keyboard answer'}}));
 render(<AgentProvider><AgentConversation/></AgentProvider>);
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Explain this reading'}});
 fireEvent.keyDown(screen.getByRole('textbox'),{key:'Enter',shiftKey:true});expect(global.fetch).not.toHaveBeenCalled();
 fireEvent.keyDown(screen.getByRole('textbox'),{key:'Enter'});
 await screen.findByText('Keyboard answer');
});
