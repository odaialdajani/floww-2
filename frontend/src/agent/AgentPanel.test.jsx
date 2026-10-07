import {render,screen,fireEvent} from "@testing-library/react";
import AgentPanel from "./AgentPanel";
let mockOpen=true;
const mockSetOpen=jest.fn();
jest.mock("./AgentProvider",()=>({useAgent:()=>({open:mockOpen,setOpen:mockSetOpen})}));
jest.mock("./AgentConversation",()=>()=> <textarea aria-label="Question"/>);
beforeEach(()=>{mockOpen=true;mockSetOpen.mockReset();});
test("Assistant stays in the workspace without blocking charts or page scrolling, and restores focus on close",()=>{
 const root=document.createElement("div");root.id="root";document.body.appendChild(root);
 const opener=document.createElement("button");opener.textContent="Chart control";document.body.appendChild(opener);opener.focus();
 document.body.style.overflow="auto";
 const view=render(<AgentPanel/>,{container:root});
 const panel=screen.getByRole("region",{name:"Ask FLOWW chat"});
 expect(root.contains(panel)).toBe(true);
 expect(panel).toHaveClass("assistant-docked");
 expect(panel).not.toHaveAttribute("aria-modal");
 expect(root).not.toHaveAttribute("inert");
 expect(document.body.style.overflow).toBe("auto");
 expect(screen.getByRole("textbox")).toHaveFocus();
 fireEvent.keyDown(panel,{key:"Escape"});expect(mockSetOpen).toHaveBeenCalledWith(false);
 mockOpen=false;view.rerender(<AgentPanel/>);
 expect(panel).toHaveAttribute("hidden");expect(opener).toHaveFocus();
 expect(root).not.toHaveAttribute("inert");expect(document.body.style.overflow).toBe("auto");
 view.unmount();root.remove();opener.remove();document.body.style.overflow="";
});
test("closing and reopening keeps the mounted chat and unsent local controls",()=>{
 const view=render(<AgentPanel/>);const question=screen.getByRole("textbox");
 question.value="Persistent local question";
 mockOpen=false;view.rerender(<AgentPanel/>);
 mockOpen=true;view.rerender(<AgentPanel/>);
 expect(screen.getByRole("textbox")).toBe(question);
 expect(question.value).toBe("Persistent local question");
});
test("closed Assistant mounts no conversation until first use",()=>{
 mockOpen=false;const view=render(<AgentPanel/>);
 expect(screen.queryByRole("textbox")).toBeNull();
 mockOpen=true;view.rerender(<AgentPanel/>);
 expect(screen.getByRole("textbox")).toBeInTheDocument();
});

test('closing one chat does not reclaim focus from a different settings popup',()=>{
 const opener=document.createElement('button');opener.textContent='Original opener';document.body.appendChild(opener);opener.focus();
 const view=render(<AgentPanel/>);
 const other=document.createElement('section');other.className='assistant-settings-dialog';other.setAttribute('data-assistant-owner','another-chat');
 const control=document.createElement('button');control.textContent='Other settings control';other.appendChild(control);document.body.appendChild(other);control.focus();
 mockOpen=false;view.rerender(<AgentPanel/>);expect(control).toHaveFocus();
 view.unmount();other.remove();opener.remove();
});

test('opening stacked chat brings its header into view without scrolling to the composer',()=>{
 mockOpen=false;const originalScroll=Element.prototype.scrollIntoView;Element.prototype.scrollIntoView=jest.fn();
 const originalFocus=HTMLTextAreaElement.prototype.focus;const focus=jest.spyOn(HTMLTextAreaElement.prototype,'focus').mockImplementation(function(options){return originalFocus.call(this,options);});
 try{
  const view=render(<div className="floww-workspace" data-chat-layout="stacked"><AgentPanel/></div>);
  mockOpen=true;view.rerender(<div className="floww-workspace" data-chat-layout="stacked"><AgentPanel/></div>);
  expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({block:'start',behavior:'auto'});
  expect(focus).toHaveBeenCalledWith({preventScroll:true});expect(screen.getByRole('textbox')).toHaveFocus();
 }finally{focus.mockRestore();Element.prototype.scrollIntoView=originalScroll;}
});
