import {MAX_SKYLIT_VIEWS,SKYLIT_VIEW_KEY,skylitViewScope,readSkylitView,writeSkylitView,captureSkylitSelection,restoreSkylitSelection} from './skylitViewPreferences';
const parameters={ticker:'SPY',timeframe:'5m',expiries:4,dte:null,expiryScope:'loaded',viewMode:'gex',localView:null};
const data=value=>({ticker:'SPY',asof:'2026-09-11T18:00:00Z',map_query:{mode:'day',expiries:4,dte:null},grid:{strikes:[650],expiries:['2026-09-18'],grid:{'2026-09-18':{650:value}}}});
const context=value=>({data:data(value),ticker:'SPY',view:'gex',metric:'raw',spot:650,windowRows:21});
const cell={ticker:'SPY',view:'gex',metric:'raw',strike:650,colKey:'2026-09-18',wall_id:null,value:123,asof:'old'};
function storage(){const map=new Map();return {getItem:key=>map.get(key)??null,setItem:(key,value)=>map.set(key,value)};}

test('preferences store only bounded display choices and selected identity, never snapshot values or protected state',()=>{
 const store=storage(),scope=skylitViewScope(parameters),identity=captureSkylitSelection(cell,context(123));
 writeSkylitView(scope,{metric:'raw',layout:'calendar',gridZoom:1.25,selection:identity,grid:data(123).grid,value:123,spot:650,tradeMode:true,scaleLock:{max:99},contractSelection:{osi:'private'},replaySnap:data(-7),account:'private'},store);
 const saved=JSON.parse(store.getItem(SKYLIT_VIEW_KEY)).entries[0].preferences;
 expect(Object.keys(saved).sort()).toEqual(['activePane','compareMode','comparePair','gridZoom','layout','metric','priceHistoryOpen','studyChoice','selection'].sort());
 expect(saved.selection).not.toHaveProperty('value');expect(saved.selection).not.toHaveProperty('asof');expect(saved.selection).not.toHaveProperty('grid');
 expect(restoreSkylitSelection(saved.selection,context(999))).toMatchObject({value:999,asof:data(999).asof});
});

test('query identity is exact while producer key order is harmless',()=>{
 const identity=captureSkylitSelection(cell,context(123));const changed=context(999);changed.data.map_query={dte:null,expiries:4,mode:'day'};
 expect(restoreSkylitSelection(identity,changed).value).toBe(999);
 changed.data.map_query={...changed.data.map_query,scalp:true};expect(restoreSkylitSelection(identity,changed)).toBeNull();
 expect(skylitViewScope({...parameters,dte:7})).not.toBe(skylitViewScope(parameters));expect(skylitViewScope({...parameters,localView:'focus'})).not.toBe(skylitViewScope(parameters));
});

test('unavailable or absent data never reconstructs a selected reading',()=>{
 const identity=captureSkylitSelection(cell,context(123));
 for(const unavailable of [null,{...data(999),stale:true},{...data(999),replay:true},{...data(999),asof:null},{...data(999),map_query:null},data(NaN)])expect(restoreSkylitSelection(identity,{...context(999),data:unavailable})).toBeNull();
 expect(captureSkylitSelection(cell,{...context(999),replay:true})).toBeNull();
});

test('bounded scope history evicts older entries and rejects malformed or blocked storage',()=>{
 const store=storage();for(let i=0;i<MAX_SKYLIT_VIEWS+5;i++)writeSkylitView(skylitViewScope({...parameters,ticker:'T'+i}),{layout:'calendar'},store);
 const saved=JSON.parse(store.getItem(SKYLIT_VIEW_KEY));expect(saved.entries).toHaveLength(MAX_SKYLIT_VIEWS);expect(saved.entries[0].key).toBe(skylitViewScope({...parameters,ticker:'T28'}));
 expect(readSkylitView(skylitViewScope({...parameters,ticker:'T0'}),store).found).toBe(false);
 expect(readSkylitView(skylitViewScope(parameters),{getItem:()=>'{bad'}).layout).toBe('profile');
 expect(readSkylitView(skylitViewScope(parameters),{getItem:()=>{throw new Error('Blocked');}}).found).toBe(false);
 expect(writeSkylitView(skylitViewScope(parameters),{layout:'calendar'},{getItem:()=>null,setItem:()=>{throw new Error('Blocked');}})).toBe(false);
});

test('malformed cached fields are stripped rather than copied forward',()=>{
 const store=storage(),scope=skylitViewScope(parameters);store.setItem(SKYLIT_VIEW_KEY,JSON.stringify({version:1,entries:[{key:scope,preferences:{layout:'calendar',metric:'invented',gridZoom:999,tradeMode:true,snapshot:data(123),selection:{...cell,query:'not-json'}}}]}));
 const restored=readSkylitView(scope,store);expect(restored).toMatchObject({layout:'calendar',metric:'raw',gridZoom:1,selection:null});
 writeSkylitView('another-query',{layout:'focus'},store);expect(store.getItem(SKYLIT_VIEW_KEY)).not.toContain('snapshot');expect(store.getItem(SKYLIT_VIEW_KEY)).not.toContain('tradeMode');
});

test('unchanged display preferences do not synchronously rewrite storage on every current-data refresh',()=>{
 const store=storage(),scope=skylitViewScope(parameters);const writes=jest.fn(store.setItem);const tracked={getItem:store.getItem,setItem:writes};
 const identity=captureSkylitSelection(cell,context(123));writeSkylitView(scope,{layout:'profile',selection:identity},tracked);
 writeSkylitView(scope,{layout:'profile',selection:captureSkylitSelection({...cell,value:999},context(999))},tracked);
 expect(writes).toHaveBeenCalledTimes(1);
});

test.each([[650],true,false,[],{},'', '   '])('saved strikes refuse malformed values: %p',strike=>{
 const current=context(321),coerced=Number(strike);current.data.grid.strikes=[coerced];current.data.grid.grid={'2026-09-18':{[coerced]:321}};current.spot=coerced;
 const identity={...cell,strike,query:JSON.stringify({dte:null,expiries:4,mode:'day'})};
 expect(restoreSkylitSelection(identity,current)).toBeNull();
 const store=storage(),scope=skylitViewScope(parameters);writeSkylitView(scope,{selection:identity},store);expect(readSkylitView(scope,store).selection).toBeNull();
});

test.each(['low','high'])('wall %s refuses malformed bounds',field=>{
 const identity={...captureSkylitSelection(cell,context(123)),wall_id:'current-wall'};
 for(const value of [[650],true,false,[],{},'', '   ']){
  const current=context(999);current.data.metrics={walls:[{wall_id:'current-wall',low:0,high:999,[field]:value}]};
  expect(restoreSkylitSelection(identity,current)).toBeNull();
 }
});

test('a malformed wall collection cannot throw or restore a saved wall',()=>{
 const identity={...captureSkylitSelection(cell,context(123)),wall_id:'current-wall'};
 for(const walls of [{},true,'current-wall',null]){
  const current=context(999);current.data.metrics={walls};
  expect(()=>restoreSkylitSelection(identity,current)).not.toThrow();expect(restoreSkylitSelection(identity,current)).toBeNull();
 }
});

test('valid numeric text is restored only from a matching current cell and wall',()=>{
 const current=context(999);current.data.metrics={walls:[{wall_id:'current-wall',low:'649.5',high:'650.5'}]};
 const identity={...captureSkylitSelection(cell,context(123)),strike:'650',wall_id:'current-wall'};
 expect(restoreSkylitSelection(identity,current)).toMatchObject({strike:650,value:999});
});


test("explicit stock study choices are additive, validated and cannot contradict their saved open state",()=>{
 const store=storage(),scope=skylitViewScope(parameters),identity=captureSkylitSelection(cell,context(123));
 writeSkylitView(scope,{studyChoice:"options",priceHistoryOpen:true,layout:"calendar",gridZoom:1.25,selection:identity},store);
 expect(readSkylitView(scope,store)).toMatchObject({studyChoice:"options",priceHistoryOpen:false,layout:"calendar",gridZoom:1.25,selection:identity});
 writeSkylitView(scope,{studyChoice:"price",priceHistoryOpen:false,layout:"calendar",gridZoom:1.25,selection:identity},store);
 expect(readSkylitView(scope,store)).toMatchObject({studyChoice:"price",priceHistoryOpen:true,selection:identity});
});
test.each([false,true,"grid",{},[],"",null])("legacy or invalid explicit stock study choice remains unknown (%p)",studyChoice=>{
 const store=storage(),scope=skylitViewScope(parameters);writeSkylitView(scope,{studyChoice,priceHistoryOpen:false,layout:"calendar"},store);
 expect(readSkylitView(scope,store)).toMatchObject({studyChoice:null,priceHistoryOpen:false,layout:"calendar"});
});
