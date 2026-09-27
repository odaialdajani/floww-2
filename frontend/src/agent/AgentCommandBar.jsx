import {useEffect} from "react";
import {useAgent} from "./AgentProvider";
export default function AgentCommandBar(){
 const a=useAgent();
 useEffect(()=>{const key=e=>{if((e.ctrlKey || e.metaKey) && e.key.toLowerCase()==="k"){e.preventDefault();a?.setOpen(v=>!v);}};
 window.addEventListener("keydown",key);return()=>window.removeEventListener("keydown",key);},[a?.setOpen]);
 return <button className="lodestar-open" onClick={()=>a?.setOpen(true)} aria-label="Open Lodestar research">Ask Lodestar <small>Ctrl / Cmd + K</small></button>;
}
