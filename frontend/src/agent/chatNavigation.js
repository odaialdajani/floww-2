import {API} from '../config/api';
import {UNIVERSE_MAX_PAGES,UNIVERSE_PAGE_LIMIT} from '../components/heatseeker/tickerUniverse';
const SYMBOL='\\$?[A-Za-z][A-Za-z0-9.-]{0,11}';
const TARGETS={chart:['heatseeker','Stock chart'],'stock chart':['heatseeker','Stock chart'],screener:['flowseeker-pro','Screener'],'activity screener':['flowseeker-pro','Screener'],'market view':['trinity','Market view'],'options map':['skylit','Options map'],'extra studies':['steal-three','Extra studies']};
/** Only explicit, bounded navigation phrases are actions. Research stays research. */
export function parseChatNavigation(question){
 if(typeof question!=='string' || question.length>2000)return null;
 const text=question.trim().replace(/[.!?]+$/,'').replace(/^(?:please\s+)?(?:can|could|would) you\s+/i,'').replace(/^please\s+/i,'');
 const match=/^(?:open|show|find)(?:\s+me)?\s+(?:the\s+)?(.+)$/i.exec(text);
 if(!match)return null;
 const target=match[1].trim();
 if(/^(?:saved answers|chat history)$/i.test(target))return {history:true,label:'Saved answers'};
 for(const [name,[page,label]] of Object.entries(TARGETS)){
  if(target.toLowerCase()===name)return {page,label};
  const after=new RegExp('^'+name+' (?:for |of )?('+SYMBOL+')$','i').exec(target);
  const before=new RegExp('^('+SYMBOL+') '+name+'$','i').exec(target);
  const stock=after?.[1] || before?.[1];
  if(stock)return {page,ticker:stock.replace(/^\$/,'').toUpperCase(),label};
 }
 return null;
}
export async function verifyNavigationTicker(symbol,get=fetch,base=API){
 if(typeof symbol!=='string' || !/^[A-Z][A-Z0-9.-]{0,11}$/.test(symbol))throw new Error('Choose a valid stock symbol.');
 const controller=new AbortController();let timer;
 try{
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new Error('This stock could not be confirmed. Check the connection and try again.'));},15000);});
  return await Promise.race([deadline,(async()=>{
   let generation;
   for(let page=1;page<=UNIVERSE_MAX_PAGES;page++){
    const url=base+'/market/catalog?'+new URLSearchParams({q:symbol,page:String(page),limit:String(UNIVERSE_PAGE_LIMIT)});
    const res=await get(url,{credentials:'omit',signal:controller.signal});
    if(!res.ok)throw new Error('This stock could not be confirmed. Check the connection and try again.');
    const data=await res.json();
    if(controller.signal.aborted)throw new Error('This stock could not be confirmed.');
    if(page>1 && data?.asof!==generation)break;
    generation=data?.asof;
    if(Array.isArray(data?.instruments) && data.instruments.some(item=>item?.symbol===symbol))return symbol;
    if(data?.has_more!==true){
     if(data?.complete_provider_catalog===true && data?.stale!==true)throw new Error("This symbol is not in the provider's available stock list.");
     break;
    }
   }
   throw new Error('This stock could not be confirmed. The available stock list is incomplete; try again.');
  })()]);
 }finally{clearTimeout(timer);controller.abort();}
}

export function isMarketQuestion(text){
 if(typeof text!=="string" || /\b(?:not|don't|do not|except|excluding)\s+(?:scan\s+)?all\s+(?:the\s+)?(?:available\s+|accessible\s+)?(?:stocks?|tickers?|symbols?|funds?|ETFs?)\b/i.test(text))return false;
 return /\b(?:all|every|each)\s+(?:the\s+)?(?:available\s+|possible\s+|accessible\s+|eligible\s+)?(?:stocks?|tickers?|symbols?|funds?|ETFs?)\b|\b(?:whole|entire)\s+market\b|\bmarket[- ]wide\b|\bacross\s+all\s+(?:available\s+)?data\b/i.test(text);
}
export function checkedChartAction(action,answer){
 if(!action || action.kind!=="open_chart" || action.view!=="heatseeker" || typeof action.ticker!=="string" || !/^[A-Z][A-Z0-9.-]{0,11}$/.test(action.ticker))return null;
 if(!Array.isArray(action.fact_ids) || !action.fact_ids.length || action.fact_ids.length>30 || !Array.isArray(answer?.facts))return null;
 const facts=action.fact_ids.map(id=>typeof id==="string"?answer.facts.find(fact=>fact?.id===id):null);
 if(facts.some(fact=>!fact || fact.ticker!==action.ticker))return null;
 return {page:"heatseeker",ticker:action.ticker,label:"Stock chart"};
}
export function prepareScreenNavigation(action){
 if(action?.page!=="flowseeker-pro" || !action.ticker)return;
 try{
  const prefs=JSON.parse(localStorage.getItem("th-prefs-v1")) || {};
  if(typeof prefs!=="object" || Array.isArray(prefs))throw new Error();
  localStorage.setItem("th-prefs-v1",JSON.stringify({...prefs,focusTicker:action.ticker}));
 }catch{throw new Error("Your screener selection could not be saved. Open Screener and choose the stock there.");}
}
