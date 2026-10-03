import React from 'react';
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import RangeAnalyticsWorkspace from './RangeAnalyticsWorkspace';
import useScreenContext from '../../agent/useScreenContext';
import complete from '../../fixtures/integration/range-analytics.v1/complete.json';
import partial from '../../fixtures/integration/range-analytics.v1/partial.json';
const response = data => ({ok:true,json:async()=>data});
function Context(){const [context]=useScreenContext();return <output data-testid="range-context">{JSON.stringify(context)}</output>;}
beforeEach(()=>{global.fetch=jest.fn(async()=>response(complete));});

test('blank window is invalid instead of silently becoming zero DTE',async()=>{
 render(<RangeAnalyticsWorkspace ticker="SPY"/>);
 fireEvent.change(screen.getByLabelText('Minimum DTE'),{target:{value:''}});
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));
 await screen.findByText(/WINDOW_OUT_OF_RANGE/);
 expect(global.fetch).not.toHaveBeenCalled();
});
test('on-demand owning axes and metrics preserve nulls, clocks and research-only admission',async()=>{
 render(<RangeAnalyticsWorkspace ticker="SPY"/>);expect(global.fetch).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));
 await screen.findByRole('grid',{name:'Raw OI GEX · strike by expiry'});
 expect(String(global.fetch.mock.calls[0][0])).toContain('/heatmap/SPY/range-analytics?min_dte=14&max_dte=60&persist=false');
 expect(screen.getByText(/Chain event time unknown/)).toBeInTheDocument();
 expect(screen.getByText(/Research only/)).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Range metric'),{target:{value:'window'}});
 expect(screen.getByRole('status')).toHaveTextContent('HISTORY_NOT_YET_RECORDED');
 expect(screen.queryByRole('grid')).not.toBeInTheDocument();
});
test('partial skipped expiry and stale provenance stay explicit, without replacement arithmetic',async()=>{
 global.fetch.mockResolvedValue(response(partial));render(<RangeAnalyticsWorkspace ticker="SPY"/>);
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));
 await screen.findByRole('grid');expect(screen.getByText(/Partial expiry coverage/)).toBeInTheDocument();
 expect(screen.getByText(`${partial.coverage.skipped[0].expiry} · reason ${partial.coverage.skipped[0].reason}`)).toBeInTheDocument();
});
test('symbol changes abort older range replies and cannot restore the previous selection',async()=>{
 let release;global.fetch.mockImplementation(()=>new Promise(resolve=>{release=resolve;}));
 const ui=render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));const signal=global.fetch.mock.calls[0][1].signal;
 ui.rerender(<><RangeAnalyticsWorkspace ticker="QQQ"/><Context/></>);expect(signal.aborted).toBe(true);
 await act(async()=>release(response(complete)));
 expect(screen.queryByRole('grid')).not.toBeInTheDocument();expect(screen.getByTestId('range-context')).not.toHaveTextContent(complete.record_id);
});
test('basis and query changes invalidate the canonical selection without invoking a model',async()=>{
 render(<><RangeAnalyticsWorkspace ticker="SPY"/><Context/></>);
 fireEvent.click(screen.getByRole('button',{name:'Load analytical range'}));await screen.findByRole('grid');
 fireEvent.click(screen.getByRole('button',{name:/^590 · 2026-10-26/}));
 await waitFor(()=>expect(JSON.parse(screen.getByTestId('range-context').textContent).selectedStrike).toBe(590));
 fireEvent.change(screen.getByLabelText('Range metric'),{target:{value:'delta_weighted'}});
 expect(JSON.parse(screen.getByTestId('range-context').textContent).selectedStrike).toBeNull();
 fireEvent.change(screen.getByLabelText('Minimum DTE'),{target:{value:'30'}});
 expect(screen.queryByRole('grid')).not.toBeInTheDocument();
 expect(JSON.parse(screen.getByTestId('range-context').textContent).snapshotId).toBeNull();
 expect(global.fetch).toHaveBeenCalledTimes(1);
});
