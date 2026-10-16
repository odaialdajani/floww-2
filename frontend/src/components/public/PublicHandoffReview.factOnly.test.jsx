import React from 'react';
import {act,render,screen,fireEvent} from '@testing-library/react';
import '@testing-library/jest-dom';
import PublicHandoffReview from './PublicHandoffReview';

const contract={osi:'SPY311017C00100000',strike:'100.0000000000000000001',expiry:'2031-10-17',type:'call',series:'SPY'};
const selection={contextVersion:2,page:'heatseeker',ticker:'SPY',snapshotId:'record-1',selectedStrike:100,selectedExpiry:contract.expiry,
 selectedContract:contract,contractResolution:'resolved',selectedWall:'wall-1',overlayMetric:'raw',metric:'gex',provider:'fixture',mapVersion:'2031-10-10T14:00:00Z',displayMode:'live'};
beforeEach(()=>{
 global.fetch=jest.fn();
 Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:jest.fn(async()=>{})}});
});
test('a resolved listed selection can prepare and copy local facts without a model turn or server write',async()=>{
 render(<PublicHandoffReview selection={selection}/>);
 fireEvent.change(screen.getByLabelText('Execution owner'),{target:{value:'PUBLIC_NATIVE_AGENT'}});
 fireEvent.click(screen.getByRole('button',{name:'Prepare fact-only brief'}));
 const brief=screen.getByLabelText('Editable Public brief');
 expect(brief.value).toContain('FACT-ONLY');
 expect(brief.value).toContain(contract.strike);
 expect(brief.value).toContain('Account: UNSET');
 expect(brief.value).toContain('Recorded bid / ask: unavailable / unavailable');
 expect(brief.value).toContain('not a server evidence hash');
 expect(screen.getByRole('button',{name:'Save manual handoff report'})).toBeDisabled();
 await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Copy brief'})));
 expect(navigator.clipboard.writeText).toHaveBeenCalledWith(brief.value);
 expect(global.fetch).not.toHaveBeenCalled();
});
test.each([{contractResolution:'pending'},{selectedStrike:101},{selectedExpiry:'2031-10-24'},{snapshotId:null},{selectedContract:{osi:contract.osi}}])('fact-only drafting refuses incomplete or conflicting selection %p',override=>{
 render(<PublicHandoffReview selection={{...selection,...override}}/>);
 fireEvent.change(screen.getByLabelText('Execution owner'),{target:{value:'PUBLIC_NATIVE_AGENT'}});
 expect(screen.getByRole('button',{name:'Prepare fact-only brief'})).toBeDisabled();
 expect(global.fetch).not.toHaveBeenCalled();
});
test('changing selection or ending the research session invalidates the local brief',()=>{
 const view=render(<PublicHandoffReview selection={selection}/>);
 fireEvent.change(screen.getByLabelText('Execution owner'),{target:{value:'PUBLIC_NATIVE_AGENT'}});
 fireEvent.click(screen.getByRole('button',{name:'Prepare fact-only brief'}));
 act(()=>window.dispatchEvent(new Event('floww-research-session-ended')));
 expect(screen.queryByLabelText('Editable Public brief')).toBeNull();
 expect(screen.getByRole('button',{name:'Prepare fact-only brief'})).toBeDisabled();
 view.rerender(<PublicHandoffReview selection={{...selection,snapshotId:'record-2'}}/>);
 expect(screen.queryByLabelText('Editable Public brief')).toBeNull();
});
