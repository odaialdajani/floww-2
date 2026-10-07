// One bounded public reading per browser session; never saved as fresh data.
const MAX_AGE=30*60*1000;let saved=null;
function copy(value,seen=new WeakMap()){
 if(value===null || typeof value!=="object")return value;
 if(seen.has(value))return seen.get(value);
 if(value instanceof Date)return new Date(value.getTime());
 const result=Array.isArray(value)?[]:{};seen.set(value,result);
 for(const key of Object.keys(value))Object.defineProperty(result,key,{value:copy(value[key],seen),enumerable:true,writable:true,configurable:true});
 return result;
}
export function clearScreenerReading(){saved=null;}
export function getScreenerReading(){
 if(!saved)return null;
 const age=Date.now()-saved.keptAt;if(age<0 || age>MAX_AGE){saved=null;return null;}
 const value=copy(saved.value);return {...value,scanMeta:{...value.scanMeta,restored:true}};
}
export function saveScreenerReading(value){
 if(!value?.scanMeta?.mode && !value?.feedReceived)return;
 const keptAt=value.scanMeta?.restored && saved?.value.scanMeta?.received===value.scanMeta.received && saved?.value.feedReceived===value.feedReceived?saved.keptAt:Date.now();
 saved={keptAt,value:copy({feed:(value.feed || []).slice(0,500),feedAt:value.feedAt,feedReceived:value.feedReceived,
  scan:(value.scan || []).slice(0,300),scanAt:value.scanAt,scanMeta:value.scanMeta})};
}
if(typeof window!=="undefined"){
 window.addEventListener("floww-research-session-ended",clearScreenerReading);
 window.addEventListener("storage",event=>{if(event.key==="floww-research-session-ended" || event.key===null)clearScreenerReading();});
}
