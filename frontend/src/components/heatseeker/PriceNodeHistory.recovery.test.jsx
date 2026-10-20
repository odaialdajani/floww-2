import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import axios from 'axios';
import PriceNodeHistory from './PriceNodeHistory';
jest.mock('axios',()=>({get:jest.fn()}));
afterEach(()=>{jest.useRealTimers();axios.get.mockReset();});
test('a failed history read has an adjacent manual retry without opening Tools',async()=>{
 axios.get.mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce({data:{ticker:'SPY',frames:[]}});
 render(<PriceNodeHistory ticker="SPY" open/>);
 await screen.findByRole('alert');const retry=screen.getByRole('button',{name:'Retry price history'});
 expect(retry).toBeVisible();expect(axios.get).toHaveBeenCalledTimes(1);
 fireEvent.click(retry);await waitFor(()=>expect(axios.get).toHaveBeenCalledTimes(2));
});
test('provider cooldown disables manual history retry until its deadline and never retries automatically',async()=>{
 jest.useFakeTimers();axios.get.mockResolvedValue({data:{ticker:'SPY',frames:[],price_status:'unavailable',price_failure:{reason:'inflight_cap',retry_after_seconds:5}}});
 render(<PriceNodeHistory ticker="SPY" open/>);await act(async()=>{});
 const retry=screen.getByRole('button',{name:'Retry price history'});expect(retry).toBeDisabled();
 fireEvent.click(retry);expect(axios.get).toHaveBeenCalledTimes(1);
 await act(async()=>jest.advanceTimersByTime(5000));expect(retry).toBeEnabled();expect(axios.get).toHaveBeenCalledTimes(1);
 fireEvent.click(retry);await act(async()=>{});expect(axios.get).toHaveBeenCalledTimes(2);
});
