/**
 * @jest-environment jsdom
 */
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import AppShell from "./AppShell";

test("renders rail + children, and routes nav clicks via onNavigate", () => {
  const onNavigate = jest.fn();
  render(<AppShell page="trinity" onNavigate={onNavigate}><div>PAGE BODY</div></AppShell>);
  expect(screen.getByText("PAGE BODY")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Stock chart/ }));
  expect(onNavigate).toHaveBeenCalledWith("heatseeker");
});

const CHAT_WIDTH_KEY='floww-assistant-pane-width';
beforeEach(()=>{localStorage.clear();document.documentElement.removeAttribute('data-sidebar-collapsed');Object.defineProperty(window,'innerWidth',{value:1440,writable:true,configurable:true});global.fetch=jest.fn();});
function openPane(){fireEvent.click(screen.getByRole('button',{name:'Open Ask FLOWW'}));return screen.getByRole('region',{name:'Ask FLOWW chat'});}

test('open chat reserves a workspace column beside the unchanged main content',()=>{
 render(<AppShell page="trinity"><button>Chart interaction</button></AppShell>);
 const main=screen.getByRole('main'),pane=openPane(),workspace=main.parentElement;
 expect(pane.parentElement).toBe(workspace);
 expect(workspace).toHaveAttribute('data-chat-layout','side');
 expect(workspace.style.gridTemplateColumns).toBe('minmax(0, 1fr) 420px');
 expect(screen.getByRole('separator',{name:'Resize chat pane'})).toHaveAttribute('aria-valuenow','420');
 expect(document.body.querySelector('.assistant-panel')).toBe(pane);
 expect(main.closest('[inert]')).toBeNull();expect(document.body.style.overflow).not.toBe('hidden');
});

test('keyboard resizing persists width, restores the whole main area on close, and keeps the same chat on reopen',()=>{
 render(<AppShell page="trinity"><button>Chart interaction</button></AppShell>);
 const pane=openPane(),handle=screen.getByRole('separator',{name:'Resize chat pane'});
 fireEvent.keyDown(handle,{key:'ArrowLeft'});expect(handle).toHaveAttribute('aria-valuenow','436');expect(localStorage.getItem(CHAT_WIDTH_KEY)).toBe('436');
 fireEvent.click(screen.getByRole('button',{name:'Close Ask FLOWW'}));
 expect(screen.getByRole('main').parentElement.style.gridTemplateColumns).toBe('minmax(0, 1fr)');
 expect(pane).toHaveAttribute('hidden');
 expect(openPane()).toBe(pane);expect(screen.getByRole('separator',{name:'Resize chat pane'})).toHaveAttribute('aria-valuenow','436');
});

test('pointer resizing moves the boundary and saves only the completed gesture',()=>{
 render(<AppShell page="trinity"><button>Chart interaction</button></AppShell>);openPane();
 const handle=screen.getByRole('separator',{name:'Resize chat pane'});handle.setPointerCapture=jest.fn();handle.releasePointerCapture=jest.fn();
 const pointer=(type,x)=>{const event=new MouseEvent(type,{bubbles:true,button:0,clientX:x});Object.defineProperty(event,'pointerId',{value:7});fireEvent(handle,event);};
 pointer('pointerdown',1000);pointer('pointermove',900);
 expect(handle).toHaveAttribute('aria-valuenow','520');expect(localStorage.getItem(CHAT_WIDTH_KEY)).toBeNull();
 pointer('pointerup',900);expect(localStorage.getItem(CHAT_WIDTH_KEY)).toBe('520');expect(handle.releasePointerCapture).toHaveBeenCalledWith(7);
});

test('viewport clamps the pane without replacing its saved width or stealing chart focus',async()=>{
 localStorage.setItem(CHAT_WIDTH_KEY,'600');render(<AppShell page="trinity"><button>Chart interaction</button></AppShell>);openPane();
 const chart=screen.getByText('Chart interaction');chart.focus();
 act(()=>{window.innerWidth=1050;window.dispatchEvent(new Event('resize'));});
 await waitFor(()=>expect(screen.getByRole('separator',{name:'Resize chat pane'})).toHaveAttribute('aria-valuenow','322'));
 expect(localStorage.getItem(CHAT_WIDTH_KEY)).toBe('600');expect(chart).toHaveFocus();
 act(()=>{window.innerWidth=500;window.dispatchEvent(new Event('resize'));});
 await waitFor(()=>expect(screen.getByRole('main').parentElement).toHaveAttribute('data-chat-layout','stacked'));
 expect(screen.getByRole('main').parentElement.style.gridTemplateColumns).toBe('minmax(0, 1fr)');
 expect(screen.queryByRole('separator',{name:'Resize chat pane'})).toBeNull();
 expect(screen.getByRole('region',{name:'Ask FLOWW chat'})).toBeInTheDocument();expect(localStorage.getItem(CHAT_WIDTH_KEY)).toBe('600');expect(chart).toHaveFocus();
});

test('sidebar collapse updates the available resize bounds without remounting the page',async()=>{
 render(<AppShell page="trinity"><input aria-label="Chart note" defaultValue="Saved local reading"/></AppShell>);openPane();
 const chart=screen.getByLabelText('Chart note');fireEvent.change(chart,{target:{value:'Keep this reading'}});
 expect(screen.getByRole('separator',{name:'Resize chat pane'})).toHaveAttribute('aria-valuemax','712');
 fireEvent.click(screen.getByRole('button',{name:'Collapse sidebar'}));
 await waitFor(()=>expect(screen.getByRole('separator',{name:'Resize chat pane'})).toHaveAttribute('aria-valuemax','720'));
 expect(screen.getByLabelText('Chart note')).toBe(chart);expect(chart).toHaveValue('Keep this reading');
});

test('resize bounds and width presets retain enough main space',()=>{
 render(<AppShell page="trinity"><button>Chart interaction</button></AppShell>);openPane();
 const handle=screen.getByRole('separator',{name:'Resize chat pane'});
 fireEvent.keyDown(handle,{key:'Home'});expect(handle).toHaveAttribute('aria-valuenow','280');
 fireEvent.keyDown(handle,{key:'ArrowLeft',shiftKey:true});expect(handle).toHaveAttribute('aria-valuenow','328');
 fireEvent.keyDown(handle,{key:'End'});expect(handle).toHaveAttribute('aria-valuenow','712');
 fireEvent.keyDown(handle,{key:'ArrowLeft'});expect(handle).toHaveAttribute('aria-valuenow','712');
 fireEvent.click(screen.getByRole('button',{name:'Compact chat'}));expect(handle).toHaveAttribute('aria-valuenow','420');
 fireEvent.click(screen.getByRole('button',{name:'Expand chat'}));expect(handle).toHaveAttribute('aria-valuenow','712');
});

test('bad stored width and unavailable width persistence cannot break resizing',()=>{
 localStorage.setItem(CHAT_WIDTH_KEY,'{"bad":"width"}');
 const original=Storage.prototype.setItem;
 jest.spyOn(Storage.prototype,'setItem').mockImplementation(function(key,value){if(key===CHAT_WIDTH_KEY)throw new Error('Width storage unavailable');return original.call(this,key,value);});
 try{
  render(<AppShell page="trinity"><button>Chart interaction</button></AppShell>);openPane();
  const handle=screen.getByRole('separator',{name:'Resize chat pane'});expect(handle).toHaveAttribute('aria-valuenow','420');
  fireEvent.keyDown(handle,{key:'ArrowLeft'});expect(handle).toHaveAttribute('aria-valuenow','436');
 }finally{Storage.prototype.setItem.mockRestore();}
});

test('container resize observations clamp layout even without a window resize',async()=>{
 const originalObserver=global.ResizeObserver;let observeResize,room=900;
 global.ResizeObserver=class{constructor(fn){observeResize=fn;}observe(){}disconnect(){}};
 const originalRect=Element.prototype.getBoundingClientRect;
 jest.spyOn(Element.prototype,'getBoundingClientRect').mockImplementation(function(){return this.classList?.contains('floww-workspace')?{width:room,left:0,right:room,top:0,bottom:800,height:800}:originalRect.call(this);});
 try{
  render(<AppShell page="trinity"><button>Chart interaction</button></AppShell>);openPane();
  await waitFor(()=>expect(screen.getByRole('separator',{name:'Resize chat pane'})).toHaveAttribute('aria-valuenow','412'));
  act(()=>{room=740;observeResize();});
  expect(screen.getByRole('main').parentElement).toHaveAttribute('data-chat-layout','stacked');expect(screen.queryByRole('separator',{name:'Resize chat pane'})).toBeNull();
 }finally{Element.prototype.getBoundingClientRect.mockRestore();global.ResizeObserver=originalObserver;}
});

test('closing during a resize releases capture and does not persist the unfinished gesture',()=>{
 render(<AppShell page="trinity"><button>Chart interaction</button></AppShell>);openPane();
 const handle=screen.getByRole('separator',{name:'Resize chat pane'});handle.releasePointerCapture=jest.fn();
 const down=new MouseEvent('pointerdown',{bubbles:true,button:0,clientX:1000});Object.defineProperty(down,'pointerId',{value:9});fireEvent(handle,down);
 const move=new MouseEvent('pointermove',{bubbles:true,clientX:900});Object.defineProperty(move,'pointerId',{value:9});fireEvent(handle,move);
 fireEvent.click(screen.getByRole('button',{name:'Close Ask FLOWW'}));
 expect(handle.releasePointerCapture).toHaveBeenCalledWith(9);expect(localStorage.getItem(CHAT_WIDTH_KEY)).toBeNull();
});

test('heatseeker viewport constraints match the docked main while ordinary pages keep document scrolling',()=>{
 const css=require('fs').readFileSync(require('path').join(__dirname,'../App.css'),'utf8');
 const ast=require('postcss').parse(css);
 const view=render(<AppShell page="heatseeker"><div><header className="ap-header">Search</header><div className="heatseeker-layout"><div className="skylit-full-dashboard">Chart rows</div></div></div></AppShell>);
 const main=screen.getByRole('main');
 const matching=[];ast.walkRules(rule=>{if(rule.nodes?.some(node=>node.prop==='height' && node.value==='100dvh') && rule.selectors.some(selector=>{try{return main.matches(selector);}catch{return false;}}))matching.push(rule);});
 expect(matching.length).toBeGreaterThan(0);
 const layout=main.querySelector('.heatseeker-layout');const fillers=[];
 ast.walkRules(rule=>{if(rule.nodes?.some(node=>node.prop==='overflow' && node.value==='hidden') && rule.selectors.some(selector=>{try{return layout.matches(selector);}catch{return false;}}))fillers.push(rule);});
 expect(fillers.length).toBeGreaterThan(0);
 view.rerender(<AppShell page="flowseeker-pro"><div>Regular screen rows</div></AppShell>);
 const regular=screen.getByRole('main');expect(matching.some(rule=>rule.selectors.some(selector=>{try{return regular.matches(selector);}catch{return false;}}))).toBe(false);
});
