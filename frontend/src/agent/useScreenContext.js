import { useLayoutEffect, useRef, useSyncExternalStore } from "react";
const EMPTY = Object.freeze({ page: "unknown", ticker: null, dte: "all", selectedContract: null, observedAt: null });
let current = EMPTY;
let currentOwner = null;
const listeners = new Set();
function releaseScreenContext(owner) {
 if (currentOwner !== owner) return;
 currentOwner = null;
 current = EMPTY;
 listeners.forEach(fn => fn());
}
export function publishScreenContext(context, owner = Symbol("screen")) {
 const next = Object.freeze({ ...EMPTY, ...context });
 currentOwner = owner;
 if (JSON.stringify(next) !== JSON.stringify(current)) {
  current = next;
  listeners.forEach(fn => fn());
 }
 return () => releaseScreenContext(owner);
}
export function usePublishScreenContext(context) {
 const owner = useRef(Symbol("screen"));
 // Publish updates without clearing the selection between ordinary renders.
 useLayoutEffect(() => {
  if (context) publishScreenContext(context, owner.current);
  else releaseScreenContext(owner.current);
 }, [context]);
 useLayoutEffect(() => {
  const token = owner.current;
  return () => releaseScreenContext(token);
 }, []);
}
const subscribe = fn => { listeners.add(fn); return () => listeners.delete(fn); };
export default function useScreenContext(external) {
 const context = useSyncExternalStore(subscribe, () => current, () => EMPTY);
 usePublishScreenContext(external);
 return [context, publishScreenContext];
}
