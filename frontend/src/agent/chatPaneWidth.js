export const CHAT_PANE_WIDTH_KEY="floww-assistant-pane-width";
export const DEFAULT_CHAT_WIDTH=420;
export const MIN_CHAT_WIDTH=280;
export const MAX_CHAT_WIDTH=720;
export const MIN_MAIN_WIDTH=480;
export const CHAT_PANE_GAP=8;

export function readChatPaneWidth(storage){
 try{
  const target=storage || window.localStorage;
  const raw=target.getItem(CHAT_PANE_WIDTH_KEY);
  if(typeof raw!=="string" || !raw.trim())return DEFAULT_CHAT_WIDTH;
  const width=Number(raw);
  return Number.isFinite(width) && width>=MIN_CHAT_WIDTH && width<=MAX_CHAT_WIDTH?Math.round(width):DEFAULT_CHAT_WIDTH;
 }catch{return DEFAULT_CHAT_WIDTH;}
}

export function saveChatPaneWidth(width,storage){
 if(!Number.isFinite(width) || width<MIN_CHAT_WIDTH || width>MAX_CHAT_WIDTH)return false;
 try{(storage || window.localStorage).setItem(CHAT_PANE_WIDTH_KEY,String(Math.round(width)));return true;}catch{return false;}
}

export function resolveChatPaneWidth(preferred,available){
 const room=Number.isFinite(available)?Math.max(0,Math.floor(available)):0;
 const side=room>=MIN_MAIN_WIDTH+MIN_CHAT_WIDTH+CHAT_PANE_GAP;
 const maximum=side?Math.min(MAX_CHAT_WIDTH,room-MIN_MAIN_WIDTH-CHAT_PANE_GAP):room;
 const minimum=side?MIN_CHAT_WIDTH:Math.min(MIN_CHAT_WIDTH,maximum);
 const desired=Number.isFinite(preferred)?preferred:DEFAULT_CHAT_WIDTH;
 const width=side?Math.round(Math.max(minimum,Math.min(maximum,desired))):maximum;
 return {layout:side?"side":"stacked",width,minWidth:minimum,maxWidth:maximum,mainWidth:side?room-width-CHAT_PANE_GAP:room};
}
