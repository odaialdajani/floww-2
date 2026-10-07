import {useCallback,useEffect,useId,useRef,useState} from "react";
import {X,Maximize2,Minimize2} from "lucide-react";
import {useAgent} from "./AgentProvider";
import AgentConversation from "./AgentConversation";
import "./AssistantWorkspace.css";
import {DEFAULT_CHAT_WIDTH,MIN_CHAT_WIDTH,MAX_CHAT_WIDTH} from "./chatPaneWidth";
export default function AgentPanel({paneWidth=DEFAULT_CHAT_WIDTH,minWidth=MIN_CHAT_WIDTH,maxWidth=MAX_CHAT_WIDTH,resizeEnabled=false,onPaneWidthChange}){
 const a=useAgent(),panel=useRef(null),previous=useRef(null);
 const panelId=useId();
 const {open,setOpen,settingsOpen,setSettingsOpen}=a || {};
 const [visited,setVisited]=useState(Boolean(open));
 const dimensions=useRef(null),drag=useRef(null);
 dimensions.current={paneWidth,minWidth,maxWidth,onPaneWidthChange};
 const canResize=resizeEnabled && typeof onPaneWidthChange==="function" && maxWidth>minWidth;
 const wide=paneWidth>Math.min(DEFAULT_CHAT_WIDTH,maxWidth);
 const endDrag=useCallback(commit=>{
  const current=drag.current;if(!current)return;drag.current=null;
  try{current.node.releasePointerCapture?.(current.pointerId);}catch{/* Capture can already be released by the browser. */}
  if(commit)dimensions.current.onPaneWidthChange?.(current.lastWidth,true);
 },[]);
 useEffect(()=>()=>endDrag(false),[endDrag]);
 useEffect(()=>{if(!open || !canResize)endDrag(false);},[open,canResize,endDrag]);
 const beginResize=e=>{
  if(!canResize || drag.current || e.button!==0 || !Number.isFinite(e.clientX))return;
  e.preventDefault();e.currentTarget.focus();
  drag.current={x:e.clientX,width:paneWidth,lastWidth:paneWidth,pointerId:e.pointerId,node:e.currentTarget};
  try{e.currentTarget.setPointerCapture?.(e.pointerId);}catch{/* Pointer capture is optional in older hosts. */}
 };
 const moveResize=e=>{
  const current=drag.current;if(!current || current.pointerId!==e.pointerId || !Number.isFinite(e.clientX))return;
  const bounds=dimensions.current;current.lastWidth=Math.max(bounds.minWidth,Math.min(bounds.maxWidth,current.width+current.x-e.clientX));
  bounds.onPaneWidthChange?.(current.lastWidth,false);
 };
 const keyResize=e=>{
  if(!canResize)return;const step=e.shiftKey?48:16;let next;
  if(e.key==="ArrowLeft")next=paneWidth+step;else if(e.key==="ArrowRight")next=paneWidth-step;else if(e.key==="Home")next=minWidth;else if(e.key==="End")next=maxWidth;else return;
  e.preventDefault();e.stopPropagation();onPaneWidthChange(Math.max(minWidth,Math.min(maxWidth,next)),true);
 };
 useEffect(()=>{
  if(!open)return;
  setVisited(true);previous.current=document.activeElement;
  const node=panel.current;const stacked=node?.parentElement?.getAttribute("data-chat-layout")==="stacked";
  if(stacked){node.scrollIntoView?.({block:"start",behavior:"auto"});node.querySelector("textarea")?.focus({preventScroll:true});}
  else node?.querySelector("textarea")?.focus();
  const key=e=>{if(e.key==="Escape" && !e.defaultPrevented){e.preventDefault();e.stopPropagation();setOpen(false);}};
  node?.addEventListener("keydown",key);
  return()=>{
   node?.removeEventListener("keydown",key);
   const focused=document.activeElement;
   const settings=focused?.closest?.(".assistant-settings-dialog");
   const ownedFocus=node?.contains(focused) || (settings && settings.getAttribute("data-assistant-owner")===node?.id);
   if(ownedFocus && previous.current?.isConnected)previous.current.focus?.();
  };
 },[open,setOpen]);
 useEffect(()=>{if(!open && settingsOpen)setSettingsOpen(false);},[open,settingsOpen,setSettingsOpen]);
 if(!a || (!visited && !open))return null;
 return <aside id={panelId} ref={panel} hidden={!open} className="lodestar-panel assistant-panel assistant-docked" style={{width:"100%",maxWidth:"100%"}} role="region" aria-label="Ask FLOWW chat">
  {resizeEnabled && <div className="assistant-resize-handle" role="separator" aria-label="Resize chat pane" aria-orientation="vertical" aria-controls={panelId} aria-valuenow={paneWidth} aria-valuemin={minWidth} aria-valuemax={maxWidth} aria-valuetext={paneWidth+" pixels wide"} aria-disabled={!canResize} tabIndex={canResize?0:-1} title="Drag to resize. Left widens chat; right narrows it." onPointerDown={beginResize} onPointerMove={moveResize} onPointerUp={e=>{if(drag.current?.pointerId===e.pointerId)endDrag(true);}} onPointerCancel={()=>endDrag(false)} onLostPointerCapture={()=>endDrag(false)} onKeyDown={keyResize}/>}
  <header className="assistant-header"><div><h2>Ask FLOWW</h2><small>Understand the reading</small></div><div className="assistant-header-actions"><button type="button" className="assistant-icon-button" aria-label={wide?"Compact chat":"Expand chat"} disabled={!canResize} onClick={()=>onPaneWidthChange(wide?Math.min(DEFAULT_CHAT_WIDTH,maxWidth):maxWidth,true)}>{wide?<Minimize2 size={16} aria-hidden="true"/>:<Maximize2 size={16} aria-hidden="true"/>}</button><button type="button" className="assistant-icon-button" aria-label="Close Ask FLOWW" onClick={()=>setOpen(false)}><X size={16} aria-hidden="true"/></button></div></header>
  <AgentConversation visible={open}/>
 </aside>;
}
