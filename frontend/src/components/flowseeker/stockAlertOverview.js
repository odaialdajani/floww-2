// Display order only: every source reading and its original facts remain intact.
export function spreadStockAlerts(rows=[],pinnedStock=null){
 const groups=new Map();
 for(const [i,row]of rows.entries()){const raw=row?.under||row?.ticker;const symbol=typeof raw==='string'&&raw.trim()?raw.trim().toUpperCase():null;const key=symbol||'unknown:'+i;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);}
 const queues=[...groups].map(([stock,items])=>({stock,items,index:0}));const output=[];let first=true;
 while(output.length<rows.length){for(const q of queues){if(first&&q.stock===pinnedStock)continue;if(q.index<q.items.length)output.push(q.items[q.index++]);}first=false;}
 return output;
}
