import {CHAT_PANE_WIDTH_KEY,readChatPaneWidth,saveChatPaneWidth,resolveChatPaneWidth} from './chatPaneWidth';
test.each([null,'','bad','Infinity','0','-500','10000','{"width":420}'])('invalid saved width falls back without an oversized pane: %s',value=>{
 expect(readChatPaneWidth({getItem:()=>value})).toBe(420);
});
test('saved widths keep their value and blocked preference storage is harmless',()=>{
 expect(readChatPaneWidth({getItem:()=> '536'})).toBe(536);
 expect(readChatPaneWidth({getItem:()=>{throw new Error('Unavailable');}})).toBe(420);
 const setItem=jest.fn();expect(saveChatPaneWidth(536,{setItem})).toBe(true);expect(setItem).toHaveBeenCalledWith(CHAT_PANE_WIDTH_KEY,'536');
 expect(saveChatPaneWidth(536,{setItem:()=>{throw new Error('Unavailable');}})).toBe(false);
 expect(saveChatPaneWidth(NaN,{setItem})).toBe(false);expect(setItem).toHaveBeenCalledTimes(1);
});
test.each([280,420,600,720,5000])('desktop room retains the main floor at requested width %s',desired=>{
 const sizing=resolveChatPaneWidth(desired,810);expect(sizing.layout).toBe('side');expect(sizing.width).toBeLessThanOrEqual(322);expect(sizing.mainWidth).toBeGreaterThanOrEqual(480);expect(sizing.width+sizing.mainWidth+8).toBe(810);
});
test.each([0,140,236,436,767])('narrow room stacks at available width %s without wider content',room=>{
 const sizing=resolveChatPaneWidth(720,room);expect(sizing.layout).toBe('stacked');expect(sizing.width).toBe(room);expect(sizing.mainWidth).toBe(room);
});
