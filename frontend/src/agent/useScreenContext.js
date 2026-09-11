import { useEffect, useSyncExternalStore } from "react";
const EMPTY = Object.freeze({ page: "unknown", ticker: null, dte: "all", selectedContract: null, observedAt: null });
let current = EMPTY;
const listeners = new Set();
export function publishScreenContext(context) {
 const next = Object.freeze({ ...EMPTY, ...context });
 if (JSON.stringify(next) === JSON.stringify(current)) return;
 current = next; listeners.forEach(fn=>fn());
}
const subscribe = fn => { listeners.add(fn); return ()=>listeners.delete(fn); };
export default function useScreenContext(external) {
 const context = useSyncExternalStore(subscribe,()=>current,()=>EMPTY);
 useEffect(()=>{if(external)publishScreenContext(external);},[external]);
 return [context,publishScreenContext];
}
