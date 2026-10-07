import {useEffect,useRef,useState} from "react";
import {createPortal} from "react-dom";
import {X} from "lucide-react";
import AgentModelSettings from "./AgentModelSettings";
const focusable=node=>[...node.querySelectorAll('button,input,textarea,select,a[href],summary,[tabindex="0"]')].filter(el=>!el.matches(':disabled') && !el.closest('[hidden]') && (!el.closest('details:not([open])') || el.tagName==='SUMMARY'));
export default function AssistantSettingsDialog({open,onClose,disabled,onSaving,endSession,endingSession,settingsPending}){
 const [visited,setVisited]=useState(open),dialog=useRef(null),previous=useRef(null);
 const close=useRef(onClose);close.current=onClose;
 useEffect(()=>{
  if(!open)return;
  setVisited(true);previous.current=document.activeElement;
  const node=dialog.current;
  node.setAttribute("data-assistant-owner",previous.current?.closest?.(".assistant-panel")?.id || "");
  const other=[...document.body.children].filter(el=>!el.contains(node));
  const prior=other.map(el=>[el,el.getAttribute('inert')]);other.forEach(el=>el.setAttribute('inert',''));
  const first=()=>focusable(node)[0];first()?.focus();
  const key=e=>{
   if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close.current();return;}
   if(e.key==='Tab'){
    const els=focusable(node),head=els[0],tail=els[els.length-1];
    if(e.shiftKey && (document.activeElement===head || !node.contains(document.activeElement))){e.preventDefault();tail?.focus();}
    else if(!e.shiftKey && (document.activeElement===tail || !node.contains(document.activeElement))){e.preventDefault();head?.focus();}
   }
  };
  const focus=e=>{if(!node.contains(e.target))first()?.focus();};
  document.addEventListener('keydown',key,true);document.addEventListener('focusin',focus);
  return()=>{
   document.removeEventListener('keydown',key,true);document.removeEventListener('focusin',focus);
   prior.forEach(([el,value])=>value===null?el.removeAttribute('inert'):el.setAttribute('inert',value));
   if(previous.current?.isConnected && !previous.current.closest('[hidden]'))previous.current.focus?.();
  };
 },[open]);
 if(!visited && !open)return null;
 return createPortal(<div className="assistant-settings-layer" hidden={!open}>
  <div className="assistant-settings-backdrop" aria-hidden="true" onClick={()=>close.current()}/>
  <section ref={dialog} className="assistant-settings-dialog" role="dialog" aria-modal={open?"true":undefined} aria-label="Ask FLOWW settings">
   <header><h2>Settings</h2><button type="button" className="assistant-icon-button" aria-label="Close settings" onClick={()=>close.current()}><X size={16} aria-hidden="true"/></button></header>
   <AgentModelSettings disabled={disabled} onSaving={onSaving} initialOpen={open}/>
   <div className="assistant-session-settings"><p>End this browser's access to saved research. Saved answers stay stored.</p><button type="button" disabled={disabled || settingsPending || endingSession} onClick={endSession}>{endingSession?"Ending session…":"End research session"}</button></div>
  </section>
 </div>,document.body);
}
