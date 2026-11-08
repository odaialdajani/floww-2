import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {ApHeader} from './App';
import axios from 'axios';
jest.mock('axios',()=>({get:jest.fn(),post:jest.fn()}));
const counts={status:'not_checked',checked_at:'2026-11-08T07:45:00Z',directory:{available:true,stale:false,total:2,optionable_total:2},options:{received_recently:0,receipt_times:[],window_seconds:300,scan_scope:'explicit_symbols',scope_size:2},provider:{last_success_at:null}};
beforeEach(()=>{localStorage.clear();Object.defineProperty(window,'innerWidth',{value:1440,writable:true,configurable:true});axios.get.mockImplementation(async()=>({data:counts}));});
test('Stock header keeps truthful counts accessible at narrow widths and preserves the same search on resize',async()=>{
 const related=jest.fn();render(<ApHeader page="heatseeker" ticker="SPY" tickers={['SPY','QQQ']} stockSearchStatus="complete" onToggleRelated={related}/>);
 await waitFor(()=>expect(screen.getByTestId('stock-feed-counts')).toHaveTextContent('2 listed'));
 expect(screen.queryByTestId('stock-diagnostics-disclosure')).toBeNull();
 const search=screen.getByRole('combobox',{name:'Search stocks'});fireEvent.change(search,{target:{value:'SP'}});
 act(()=>{window.innerWidth=800;window.dispatchEvent(new Event('resize'));});
 const disclosure=screen.getByTestId('stock-diagnostics-disclosure');expect(disclosure).not.toHaveAttribute('open');
 disclosure.querySelector('summary').click();expect(disclosure).toHaveAttribute('open');
 expect(screen.getByTestId('stock-feed-counts')).toHaveTextContent('0 stocks checked of 2 configured symbols');
 expect(screen.getByRole('combobox',{name:'Search stocks'})).toBe(search);expect(search).toHaveValue('SP');
 fireEvent.click(screen.getByRole('button',{name:'Related stocks and funds'}));expect(related).toHaveBeenCalledTimes(1);
 expect(screen.getByLabelText('Data and account settings')).toBeInTheDocument();
 act(()=>{window.innerWidth=1440;window.dispatchEvent(new Event('resize'));});
 expect(screen.queryByTestId('stock-diagnostics-disclosure')).toBeNull();expect(screen.getByTestId('stock-feed-counts')).toHaveTextContent('2 with options');expect(search).toHaveValue('SP');
 expect(axios.post).not.toHaveBeenCalled();
});
test('other pages retain their existing inline feed counts at narrow widths',async()=>{
 window.innerWidth=800;render(<ApHeader page="trinity" ticker="SPY" tickers={['SPY']}/>);
 await waitFor(()=>expect(screen.getByTestId('stock-feed-counts')).toHaveTextContent('2 listed'));
 expect(screen.queryByTestId('stock-diagnostics-disclosure')).toBeNull();
});
