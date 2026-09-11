import {useEffect, useRef, useState} from "react";
import {API} from "../config/api";

export const THINKING_LABELS = {low:"Quick", medium:"Balanced", high:"Deep", xhigh:"Deeper", max:"Deepest"};
export const SPEED_LABELS = {default:"Standard", priority:"Fast (uses more allowance)"};

export default function AgentModelSettings({disabled=false, onSaving=()=>{}}) {
 const [open,setOpen]=useState(false),[loading,setLoading]=useState(false),[models,setModels]=useState([]);
 const [selected,setSelected]=useState(null),[saved,setSaved]=useState(null),[message,setMessage]=useState("");
 const [usage,setUsage]=useState(null);
 const epoch=useRef(0),controller=useRef(null);
 const uncertain=useRef(false);
 const savingCallback=useRef(onSaving);savingCallback.current=onSaving;
 useEffect(()=>{
  const clear=()=>{epoch.current++;controller.current?.abort();uncertain.current=false;setOpen(false);setLoading(false);setModels([]);setSelected(null);setSaved(null);setUsage(null);setMessage("");savingCallback.current(false);};
  const storage=e=>{if(e.key==="floww-research-session-ended" && e.newValue)clear();};
  window.addEventListener("floww-research-session-ended",clear);window.addEventListener("storage",storage);
  return ()=>{epoch.current++;controller.current?.abort();savingCallback.current(false);window.removeEventListener("floww-research-session-ended",clear);window.removeEventListener("storage",storage);};
 },[]);
 const load=async()=>{
  if(loading || disabled)return;
  setOpen(true);setLoading(true);onSaving(true);setMessage("");const current=++epoch.current;
  const abort=new AbortController();controller.current=abort;
  const timer=setTimeout(()=>abort.abort(),30000);
  try{
   const session=await fetch(`${API}/agent/session`,{method:"POST",credentials:"include",signal:abort.signal});
   if(!session.ok)throw new Error();
   const response=await fetch(`${API}/agent/models`,{credentials:"include",signal:abort.signal});
   if(!response.ok)throw new Error();
   const data=await response.json();
   if(epoch.current===current){
    uncertain.current=false;
    setModels(data.models);setSaved(data.selected);setUsage(data.usage);
    const supported=data.models.find(m=>m.id===data.selected?.model);
    if(supported && supported.efforts.includes(data.selected.effort) && supported.speeds.includes(data.selected.speed))setSelected(data.selected);
    else if(supported){setSelected({model:supported.id,effort:supported.default_effort,speed:"default"});setMessage("Your saved depth or speed is unavailable. Choose and save a replacement.");}
    else if(data.models.length){const first=data.models[0];setSelected({model:first.id,effort:first.default_effort,speed:"default"});setMessage("Your saved model is unavailable. Choose and save a replacement.");}
    else setSelected(null);
   }
  }catch{if(epoch.current===current)setMessage("AI choices are unavailable. Check that Codex is signed in with ChatGPT on this computer.");}
  finally{clearTimeout(timer);if(epoch.current===current){setLoading(false);onSaving(uncertain.current);}}
 };
 const changeModel=id=>{
  const model=models.find(m=>m.id===id);
  if(!model)return;
  setSelected({model:id,effort:model.efforts.includes(selected.effort)?selected.effort:model.default_effort,
               speed:model.speeds.includes(selected.speed)?selected.speed:"default"});setMessage("");
 };
 const save=async()=>{
  if(disabled || loading)return;
  const current=++epoch.current;setLoading(true);onSaving(true);setMessage("");
  let confirmed=false;
  const abort=new AbortController();controller.current=abort;const timer=setTimeout(()=>abort.abort(),30000);
  try{
   const response=await fetch(`${API}/agent/prefs`,{method:"PUT",credentials:"include",signal:abort.signal,
    headers:{"Content-Type":"application/json"},body:JSON.stringify({ai_settings:selected})});
   if(!response.ok)throw new Error();
   if(epoch.current===current){confirmed=true;setSaved(selected);setMessage("Saved for your next question.");}
  }catch{if(epoch.current===current){uncertain.current=true;setMessage("Your new AI choice was not confirmed. Reload choices before asking.");}}
  finally{clearTimeout(timer);if(epoch.current===current){setLoading(false);onSaving(!confirmed);}}
 };
 const model=models.find(m=>m.id===selected?.model);
 const changed=selected && JSON.stringify(selected)!==JSON.stringify(saved);
 return <div className="lodestar-model-settings">
  <button type="button" disabled={disabled || loading} onClick={()=>open?setOpen(false):load()} aria-expanded={open}>
   {loading?"Checking AI choices…":"AI choices · ChatGPT login"}
  </button>
  {open && <div>
   {model && <fieldset disabled={disabled || loading}>
    <legend>Choose how your next question is answered</legend>
    <label>Model<select value={selected.model} onChange={e=>changeModel(e.target.value)}>
     {models.map(m=><option key={m.id} value={m.id}>{m.label}</option>)}
    </select></label>
    <label>Thinking depth<select value={selected.effort} onChange={e=>{setSelected({...selected,effort:e.target.value});setMessage("");}}>
     {model.efforts.map(e=><option key={e} value={e}>{THINKING_LABELS[e] || e}</option>)}
    </select></label>
    <label>Speed<select value={selected.speed} onChange={e=>{setSelected({...selected,speed:e.target.value});setMessage("");}}>
     {model.speeds.map(s=><option key={s} value={s}>{SPEED_LABELS[s] || s}</option>)}
    </select></label>
    <button type="button" onClick={save} disabled={!changed}>Save AI choice</button>
    {changed && <small>Unsaved choice. Questions use your last saved choice.</small>}
   </fieldset>}
   <small>Uses your ChatGPT allowance. Dollar cost is not reported. These are the settings supported by your login.</small>
   {usage && <small>{usage.calls} of {usage.daily_limit} app calls used today. Cancelled or uncertain calls still count.</small>}
   {message && <p role="status">{message}</p>}
   {!loading && <button type="button" disabled={disabled} onClick={load}>Reload choices</button>}
  </div>}
 </div>;
}
