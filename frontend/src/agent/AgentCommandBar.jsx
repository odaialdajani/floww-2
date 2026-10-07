import {useEffect} from "react";
import {MessageSquare} from "lucide-react";
import {useAgent} from "./AgentProvider";
import "./AssistantWorkspace.css";
export default function AgentCommandBar(){
 const {setOpen,settingsOpen}=useAgent() || {};
 useEffect(()=>{const key=e=>{if((e.ctrlKey || e.metaKey) && e.key.toLowerCase()==="k" && !settingsOpen){e.preventDefault();setOpen?.(v=>!v);}};
 window.addEventListener("keydown",key);return()=>window.removeEventListener("keydown",key);},[setOpen,settingsOpen]);
 return <button type="button" className="lodestar-open assistant-open" onClick={()=>setOpen?.(true)} aria-label="Open Ask FLOWW" title="Ask FLOWW (Ctrl / Cmd + K)"><MessageSquare size={15} aria-hidden="true"/>Ask FLOWW</button>;
}
