import React,{useEffect,useRef} from 'react';
import {Settings} from 'lucide-react';
import './DataAccountMenu.css';
export default function DataAccountMenu({ticker,data,userEmail,onSignOut}) {
 const ref=useRef(null);
 useEffect(()=>{const close=event=>{if(ref.current?.open&&!ref.current.contains(event.target))ref.current.open=false;};document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close);},[]);
 const owns=data?.ticker===ticker||data?.symbol===ticker;
 const source=owns&&typeof data?.data_source==='string'?data.data_source.replace(/[_-]/g,' '):null;
 const rawTime=owns?(data.event_time||data.observed_at||data.asof):null;
 const time=typeof rawTime==='string'&&/(?:Z|[+-]\d{2}:\d{2})$/.test(rawTime)&&Number.isFinite(Date.parse(rawTime))?new Date(rawTime).toLocaleString('en-US',{timeZone:'America/New_York'}):null;
 return <details ref={ref} className="floww-account-menu" onKeyDown={event=>{if(event.key==='Escape'){ref.current.open=false;ref.current.querySelector('summary')?.focus();}}}>
  <summary aria-label="Data and account settings" title="Data and account settings"><Settings size={16} aria-hidden="true"/></summary>
  <div className="floww-account-menu-content"><strong>Data & account</strong><dl><dt>Selected stock</dt><dd>{ticker}</dd><dt>Current stock reading</dt><dd>{source||'Source unavailable'}</dd><dt>Reading time</dt><dd>{time?time+' New York':'Time unavailable'}</dd></dl>{userEmail&&<p>{userEmail}</p>}<button type="button" onClick={onSignOut}>Sign out</button></div>
 </details>;
}
