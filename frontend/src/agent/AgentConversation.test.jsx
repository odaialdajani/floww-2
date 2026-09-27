import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import AgentProvider from './AgentProvider';
import AgentConversation from './AgentConversation';
import {publishScreenContext} from './useScreenContext';

jest.mock('./AgentModelSettings',()=>()=>null);
beforeAll(()=>Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true}));

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
