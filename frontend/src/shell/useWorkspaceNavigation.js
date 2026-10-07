import { useCallback, useEffect, useRef, useState } from "react";
import { NAV_ITEMS } from "./navConfig";
const workspaceIds = new Set(NAV_ITEMS.map(item => item.id));
const ENTRY_KEY="flowwWorkspaceHistory",SESSION_KEY="floww-workspace-history-v1";
export function readWorkspace() {
 const id=new URLSearchParams(window.location.search).get("page");return workspaceIds.has(id)?id:"flowseeker-pro";
}
function savedSession(){try{return JSON.parse(sessionStorage.getItem(SESSION_KEY));}catch{return null;}}
function validIndex(value){return Number.isSafeInteger(value)&&value>=0&&value<=10000;}
function readEntry(chain){const entry=window.history.state?.[ENTRY_KEY];return entry&&entry.chain===chain&&validIndex(entry.index)?entry.index:null;}
function save(chain,max){try{sessionStorage.setItem(SESSION_KEY,JSON.stringify({chain,max}));}catch{}}
function tag(chain,index){const state=window.history.state;const base=state&&typeof state==='object'&&!Array.isArray(state)?state:{};return {...base,[ENTRY_KEY]:{chain,index}};}
function initialHistory(){
 const saved=savedSession(),index=typeof saved?.chain==='string'?readEntry(saved.chain):null;
 if(index!==null&&validIndex(saved.max)&&saved.max>=index)return {chain:saved.chain,index,max:saved.max};
 const chain=Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);save(chain,0);window.history.replaceState(tag(chain,0),'',window.location.href);return {chain,index:0,max:0};
}
export default function useWorkspaceNavigation(){
 const [page,setPage]=useState(readWorkspace),[position,setPosition]=useState(initialHistory),current=useRef(position);current.current=position;
 useEffect(()=>{
  const restore=()=>{setPage(readWorkspace());const previous=current.current,index=readEntry(previous.chain);if(index===null){const next=initialHistory();current.current=next;setPosition(next);}else{const next={...previous,index,max:Math.max(previous.max,index)};current.current=next;setPosition(next);save(next.chain,next.max);}};
  window.addEventListener('popstate',restore);return()=>window.removeEventListener('popstate',restore);
 },[]);
 const navigate=useCallback(id=>{
  if(!workspaceIds.has(id))return;
  const url=new URL(window.location.href);
  if(url.searchParams.get('page')!==id){
   const previous=current.current,index=Math.min(10000,previous.index+1),next={chain:previous.chain,index,max:index};url.searchParams.set('page',id);
   window.history.pushState(tag(next.chain,index),'',url.pathname+url.search+url.hash);current.current=next;setPosition(next);save(next.chain,next.max);
  }setPage(id);
 },[]);
 const back=useCallback(()=>{if(current.current.index>0)window.history.back();},[]);
 const forward=useCallback(()=>{if(current.current.index<current.current.max)window.history.forward();},[]);
 return [page,navigate,{canBack:position.index>0,canForward:position.index<position.max,back,forward}];
}
