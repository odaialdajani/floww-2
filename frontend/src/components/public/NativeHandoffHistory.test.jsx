import React from 'react';
import {act,render,screen,fireEvent,waitFor} from '@testing-library/react';
import NativeHandoffHistory from './NativeHandoffHistory';

test('private report history is authenticated and never presented as a verified native order',async()=>{
 global.fetch=jest.fn(async()=>({ok:true,json:async()=>({handoffs:[{handoff_id:'report-1',workflow_reference:'operator-ref',reported_status:'reported_active',created_at:'2026-10-02T15:00:00Z'}]})}));
 render(<NativeHandoffHistory/>);
 expect(global.fetch).not.toHaveBeenCalled();
 await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Load private handoff history'})));
 expect(global.fetch.mock.calls[0][1].credentials).toBe('include');
 expect(screen.getByText('operator-ref')).toBeVisible();
 expect(screen.getByText(/reported_active.*unverified/)).toBeVisible();
 act(()=>window.dispatchEvent(new Event('floww-research-session-ended')));
 expect(screen.queryByText('operator-ref')).not.toBeInTheDocument();
});

test('a late history response cannot repopulate a revoked view',async()=>{
 let release;
 global.fetch=jest.fn(()=>new Promise(resolve=>{release=resolve;}));
 render(<NativeHandoffHistory/>);
 fireEvent.click(screen.getByRole('button',{name:'Load private handoff history'}));
 await waitFor(()=>expect(release).toBeTruthy());
 act(()=>window.dispatchEvent(new Event('floww-research-session-ended')));
 await act(async()=>release({ok:true,json:async()=>({handoffs:[{handoff_id:'old',workflow_reference:'old-owner'}]})}));
 expect(screen.queryByText('old-owner')).not.toBeInTheDocument();
});
