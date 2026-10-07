import { useState, useEffect, useCallback, useRef } from "react";
import Sidebar from "./Sidebar";
import ProblemStatus from "../diagnostics/ProblemStatus";
import AgentProvider, { useAgent } from "../agent/AgentProvider";
import AgentPanel from "../agent/AgentPanel";
import AgentCommandBar from "../agent/AgentCommandBar";
import { SIDEBAR_KEY } from "./navConfig";
import { CHAT_PANE_GAP, readChatPaneWidth, resolveChatPaneWidth, saveChatPaneWidth } from "../agent/chatPaneWidth";

function readCollapsed() {
  // Same source the Sidebar itself reads (2026-09-04): the DOM attribute
  // handshake alone can disagree on first paint (attribute unset until the
  // Sidebar mounts), leaving a ~176px dead gutter beside the rail.
  try {
    const v = localStorage.getItem(SIDEBAR_KEY);
    if (v != null) return v === "true";
  } catch { /* private mode â€” fall through to the attribute */ }
  return document.documentElement.getAttribute("data-sidebar-collapsed") === "true";
}

function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === "attributes" && m.attributeName === "data-sidebar-collapsed") {
          setCollapsed(document.documentElement.getAttribute("data-sidebar-collapsed") === "true");
        }
      }
    });
    observer.observe(document.documentElement, { attributes: true });
    return () => observer.disconnect();
  }, []);
  return collapsed;
}

function viewportWidth(){return document.documentElement.clientWidth || window.innerWidth || 0;}

function Workspace({collapsed,children}){
 const agent=useAgent(),workspace=useRef(null);
 const railWidth=collapsed?64:240;
 const [preferred,setPreferred]=useState(readChatPaneWidth);
 const [measured,setMeasured]=useState(()=>Math.max(0,viewportWidth()-railWidth));
 useEffect(()=>{
  const measure=()=>{
   const available=Math.max(0,viewportWidth()-railWidth);
   const actual=workspace.current?.getBoundingClientRect().width;
   setMeasured(actual>0?Math.min(actual,available):available);
  };
  measure();window.addEventListener("resize",measure);
  const observer=typeof ResizeObserver==="function"?new ResizeObserver(measure):null;
  if(workspace.current)observer?.observe(workspace.current);
  return()=>{window.removeEventListener("resize",measure);observer?.disconnect();};
 },[railWidth]);
 const available=Math.min(measured,Math.max(0,viewportWidth()-railWidth));
 const sizing=resolveChatPaneWidth(preferred,available);
 const changeWidth=useCallback((width,persist=true)=>{
  if(!Number.isFinite(width))return;
  const next=resolveChatPaneWidth(width,available).width;
  setPreferred(next);if(persist)saveChatPaneWidth(next);
 },[available]);
 const layout=agent.open?sizing.layout:"closed";
 return <div ref={workspace} className="floww-workspace" data-chat-layout={layout}
  style={{marginLeft:railWidth,minWidth:0,minHeight:"100dvh",display:"grid",gridTemplateColumns:layout==="side"?"minmax(0, 1fr) "+sizing.width+"px":"minmax(0, 1fr)",columnGap:layout==="side"?CHAT_PANE_GAP:0,"--assistant-pane-width":sizing.width+"px"}}>
  <main className="floww-workspace-main" style={{minWidth:0,display:"flex",flexDirection:"column",minHeight:"100dvh"}}>{children}</main>
  <AgentPanel paneWidth={sizing.width} minWidth={sizing.minWidth} maxWidth={sizing.maxWidth} resizeEnabled={layout==="side"} onPaneWidthChange={changeWidth}/>
  <AgentCommandBar/><ProblemStatus/>
 </div>;
}

export default function AppShell({ page, onNavigate, children, userEmail, userTier }) {
 const collapsed=useSidebarCollapsed();
 return <AgentProvider onNavigate={onNavigate}>
  <div className="min-h-screen floww-application" style={{background:"var(--bg-page)"}}>
   <Sidebar page={page} onNavigate={onNavigate} userEmail={userEmail} userTier={userTier}/>
   <Workspace collapsed={collapsed}>{children}</Workspace>
  </div>
 </AgentProvider>;
}
