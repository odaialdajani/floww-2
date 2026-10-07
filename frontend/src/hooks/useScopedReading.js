import {useCallback,useRef,useState} from "react";

// Each reply belongs to the exact request generation. Optional retention is
// per hook, bounded, and never changes the value's original observation time.
export function useScopedReading(scope,{retain=false,maxAgeMs=30*60*1000,maxEntries=8}={}){
 const current=useRef({scope}),cache=useRef(new Map());
 if(current.current.scope!==scope)current.current={scope};
 const request=current.current;
 const [saved,setSaved]=useState(null);
 const ageLimit=Number.isFinite(maxAgeMs)?Math.max(1,Math.min(30*60*1000,maxAgeMs)):30*60*1000;
 const entryLimit=Number.isInteger(maxEntries)?Math.max(1,Math.min(8,maxEntries)):8;
 const save=useCallback(value=>{
  if(current.current!==request)return;
  if(retain){
   cache.current.delete(scope);
   if(value!=null)cache.current.set(scope,{value,savedAt:Date.now()});
   while(cache.current.size>entryLimit)cache.current.delete(cache.current.keys().next().value);
  }
  setSaved({request,value});
 },[request,retain,scope,entryLimit]);
 const retained=retain && saved?.request!==request?cache.current.get(scope):null;
 const usable=retained && Date.now()-retained.savedAt>=0 && Date.now()-retained.savedAt<=ageLimit;
 if(retained && !usable)cache.current.delete(scope);
 return [saved?.request===request?saved.value:usable?retained.value:null,save,Boolean(usable)];
}
