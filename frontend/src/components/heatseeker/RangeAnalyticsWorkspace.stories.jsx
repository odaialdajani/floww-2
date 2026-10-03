import React from 'react';
import {expect,userEvent,within} from 'storybook/test';
import RangeAnalyticsWorkspace from './RangeAnalyticsWorkspace';
import complete from '../../fixtures/integration/range-analytics.v1/complete.json';
import partial from '../../fixtures/integration/range-analytics.v1/partial.json';

export default {
 title:'Solstice/Analytical range',component:RangeAnalyticsWorkspace,args:{ticker:'SPY'},
 parameters:{layout:'fullscreen',docs:{description:{component:'Production range consumer using verbatim Cline range-analytics.v1 synthetic fixtures. No capture, history reconstruction, provider or execution call. Shape admission is not evidence-integrity verification.'}}},
 decorators:[Story=><div style={{padding:16,minWidth:0}}><Story/></div>],
 beforeEach({parameters}){
  const original=globalThis.fetch;
  globalThis.fetch=async url=>{
   if(!String(url).includes('/range-analytics?') || !String(url).includes('persist=false'))throw new Error('Unexpected preview request');
   return {ok:true,json:async()=>parameters.rangeFixture || complete};
  };
  return()=>{globalThis.fetch=original;};
 },
};
async function load(canvasElement){
 const canvas=within(canvasElement);
 await userEvent.click(canvas.getByRole('button',{name:'Load analytical range'}));
 await expect(canvas.findByRole('grid')).resolves.toBeInTheDocument();
 return canvas;
}
export const Complete={async play({canvasElement}){
 const c=await load(canvasElement);
 const first=c.getByRole('button',{name:/^590 · 2026-10-26/});
 await userEvent.click(first);await userEvent.keyboard('{ArrowRight}');
 await expect(c.getByRole('button',{name:/^590 · 2026-11-09/})).toHaveFocus();
 await expect(c.getByRole('complementary',{name:'Range selection review'})).toHaveTextContent('590 USD · 2026-10-26');
 await expect(c.getByRole('button',{name:'Range replay unavailable'})).toBeDisabled();
}};
export const PartialCoverage={parameters:{rangeFixture:partial},async play({canvasElement}){
 const c=await load(canvasElement);
 await expect(c.getByText(/Partial expiry coverage/)).toBeInTheDocument();
 await expect(c.getByText(`${partial.coverage.skipped[0].expiry} · reason ${partial.coverage.skipped[0].reason}`)).toBeInTheDocument();
 await expect(c.getAllByRole('button',{name:/Unavailable$/}).length).toBeGreaterThan(0);
}};
export const WindowUnavailable={async play({canvasElement}){
 const c=await load(canvasElement);await userEvent.selectOptions(c.getByLabelText('Range metric'),'window');
 await expect(c.getByRole('status')).toHaveTextContent('HISTORY_NOT_YET_RECORDED');
 await expect(c.queryByRole('grid')).not.toBeInTheDocument();
}};
export const ReversedWindowRefused={async play({canvasElement}){
 const c=within(canvasElement);
 await userEvent.clear(c.getByLabelText('Minimum DTE'));await userEvent.type(c.getByLabelText('Minimum DTE'),'60');
 await userEvent.clear(c.getByLabelText('Maximum DTE'));await userEvent.type(c.getByLabelText('Maximum DTE'),'14');
 await userEvent.click(c.getByRole('button',{name:'Load analytical range'}));
 await expect(c.getByRole('status')).toHaveTextContent('REVERSED_WINDOW');
 await expect(c.queryByRole('grid')).not.toBeInTheDocument();
}};
