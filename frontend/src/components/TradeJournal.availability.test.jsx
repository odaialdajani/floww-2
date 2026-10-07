import React from 'react';
import {render,screen,waitFor} from '@testing-library/react';
import TradeJournal from './TradeJournal';
beforeEach(()=>{localStorage.clear();global.fetch=jest.fn();});
afterEach(()=>jest.restoreAllMocks());
test('an unavailable server history does not claim no trades or a verified zero profit',async()=>{
 fetch.mockResolvedValue({ok:false});render(<TradeJournal ticker="SPY"/>);expect(await screen.findByText(/Server history is unavailable/)).toBeVisible();expect(screen.queryByText('No trades yet')).not.toBeInTheDocument();expect(screen.queryByText('$+0')).not.toBeInTheDocument();expect(screen.getByText('Saved records unavailable')).toBeVisible();
});
test('a malformed successful response stays unavailable rather than becoming an empty history',async()=>{
 fetch.mockResolvedValue({ok:true,json:async()=>({trades:{wrong:'shape'}})});render(<TradeJournal ticker="SPY"/>);expect(await screen.findByText(/Server history is unavailable/)).toBeVisible();expect(screen.queryByText('No trades yet')).not.toBeInTheDocument();
});
test('known saved entries remain visible with an explicit coverage limit while the server is offline',async()=>{
 localStorage.setItem('floww_trades_v2',JSON.stringify([{id:'manual',ticker:'SPY',type:'call',action:'buy',quantity:1,entry_price:1,exit_price:2,entry_date:'2026-10-01',exit_date:'2026-10-02'}]));fetch.mockRejectedValue(new Error('offline'));render(<TradeJournal ticker="SPY"/>);expect(await screen.findByText(/Server history is unavailable/)).toBeVisible();expect(screen.getAllByText(/\$\+?100/).length).toBeGreaterThan(0);expect(screen.getByText(/Figures cover loaded records only/)).toBeVisible();
});
test('a confirmed empty server and readable empty local cache can show no saved trades',async()=>{
 fetch.mockResolvedValue({ok:true,json:async()=>({trades:[]})});render(<TradeJournal ticker="SPY"/>);expect(await screen.findByText('No trades yet')).toBeVisible();await waitFor(()=>expect(screen.queryByText(/Loading saved records/)).not.toBeInTheDocument());
});
