import React from 'react';
import {render,screen,within} from '@testing-library/react';
import AgentPanelAnswer from './AgentPanelAnswer';
const turn=extra=>({ticker:'SPY',status:'completed',saved:true,answer:{summary:'Current saved reading',history_baseline:{date:'2026-10-01'},sections:[{name:'What changed',text:'Compared with the saved source observation at 2026-10-01T19:30:00+00:00. Price change: +3 USD.',fact_ids:[],status:'degraded'}],...extra}});
test('the requested dated comparison is visible before opening source details',()=>{
 render(<AgentPanelAnswer turn={turn()}/>);
 expect(screen.getByRole('region',{name:'Saved date comparison'})).toBeVisible();
 expect(screen.getByRole('region',{name:'Saved date comparison'})).toHaveTextContent('2026-10-01');
 expect(within(screen.getByRole('region',{name:'Saved date comparison'})).getByText(/Compared with the saved source observation/)).toBeVisible();
});
test('a missing dated observation is visible and never becomes a zero change',()=>{
 render(<AgentPanelAnswer turn={turn({sections:[{name:'What changed',text:'No compatible saved observation was available on 2026-10-01',status:'unavailable',fact_ids:[]}]})}/>);
 expect(within(screen.getByRole('region',{name:'Saved date comparison'})).getByText('No compatible saved observation was available on 2026-10-01')).toBeVisible();
 expect(screen.queryByText(/Price change:.*0 USD/)).not.toBeInTheDocument();
});
test.each([undefined,null,'legacy'])('a retrieved answer with unknown completion %s is readable but cannot claim checked AI',status=>{
 render(<AgentPanelAnswer turn={{ticker:'SPY',status,answer:{summary:'Actual older answer',mode:'model-assisted',model_status:'Checked interpretation'}}}/>);
 expect(screen.getByText('Actual older answer')).toBeVisible();
 expect(screen.queryByText('AI explanation checked')).not.toBeInTheDocument();
 expect(screen.getByText('Saved answer status unknown')).toBeVisible();
});
test.each([{date:'2026-02-30'},{date:{bad:true}},[]])('unusable saved date metadata is marked incomplete without losing the reading: %j',history_baseline=>{
 render(<AgentPanelAnswer turn={turn({history_baseline})}/>);
 expect(screen.getByText('Current saved reading')).toBeVisible();
 expect(screen.getByText(/Some saved answer details are incomplete/)).toBeVisible();
});

test('unknown completion cannot label supported older text as a checked assessment',()=>{
 render(<AgentPanelAnswer turn={{ticker:'SPY',status:'legacy',_savedStateUnverified:true,answer:{summary:'Original older answer',model_sections:[{name:'Verdict',text:'An original older interpretation',fact_ids:['f1']}],facts:[{id:'f1',ticker:'SPY',metric:'Underlying price',value:93,unit:'USD',source:'fixture',status:'ok'}]}}}/>);
 expect(screen.queryByRole('region',{name:'Checked assessment'})).not.toBeInTheDocument();
 const region=screen.getByRole('region',{name:'Saved interpretation'});expect(region).toBeVisible();
 expect(within(region).getByText('An original older interpretation')).toBeVisible();
});

test("incomplete saved date keeps its interpretation unverified",()=>{
 render(<AgentPanelAnswer turn={{ticker:"SPY",status:"completed",answer:{history_baseline:{date:"2026-02-30"},summary:"Original older answer",model_sections:[{name:"Verdict",text:"Original limited interpretation",fact_ids:["f1"]}],facts:[{id:"f1",ticker:"SPY",metric:"Underlying price",value:93,unit:"USD",source:"fixture",status:"ok"}]}}}/>);
 expect(screen.queryByRole("region",{name:"Checked assessment"})).not.toBeInTheDocument();
 expect(within(screen.getByRole("region",{name:"Saved interpretation"})).getByText("Original limited interpretation")).toBeVisible();
});
