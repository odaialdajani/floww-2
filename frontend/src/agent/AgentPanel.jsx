import {useEffect,useRef} from "react";
import {createPortal} from "react-dom";
import {useAgent} from "./AgentProvider";
import AgentConversation from "./AgentConversation";
export default function AgentPanel(){
 const a=useAgent(),dialog=useRef(null),previous=useRef(null);
 useEffect(()=>{
  if(!a?.open)return;
  previous.current=document.activeElement;
  const root=document.getElementById("root"),oldInert=root?.getAttribute("inert"),oldOverflow=document.body.style.overflow;
  root?.setAttribute("inert","");document.body.style.overflow="hidden";
  const node=dialog.current;node?.querySelector("textarea")?.focus();
  const key=e=>{if(e.key==="Escape"){a.setOpen(false);e.stopPropagation();}if(e.key==="Tab"){
   const els=[...node.querySelectorAll('button:not(:disabled),textarea,input:not(:disabled),select:not(:disabled),a[href],summary,[tabindex="0"]')].filter(el=>!el.closest('details:not([open])') || el.tagName==='SUMMARY');const first=els[0],last=els[els.length-1];
   if(e.shiftKey && document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey && document.activeElement===last){e.preventDefault();first?.focus();}
  }};
  node.addEventListener("keydown",key);return()=>{node.removeEventListener("keydown",key);document.body.style.overflow=oldOverflow;if(root){if(oldInert===null)root.removeAttribute("inert");else root.setAttribute("inert",oldInert);}previous.current?.focus?.();};
 },[a?.open]);
 if(!a?.open)return null;
 return createPortal(<><div className="lodestar-backdrop" aria-hidden="true" onClick={()=>a.setOpen(false)} /><aside ref={dialog} className="lodestar-panel" role="dialog" aria-modal="true" aria-label="Lodestar research">
  <header><h2>Lodestar</h2><button onClick={()=>a.setOpen(false)}>Close</button></header><AgentConversation/>
 </aside></>,document.body);
}
