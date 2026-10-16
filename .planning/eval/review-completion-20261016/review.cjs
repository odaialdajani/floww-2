const path=require('path');
const fs=require('fs');
const assert=require('assert/strict');
const ROOT=path.resolve(__dirname,'../../..');
const {chromium}=require(path.join(ROOT,'frontend/node_modules/playwright'));
const OUTPUT=process.env.FLOWW_REVIEW_OUTPUT || __dirname;
const rect=e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};};

(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const report={passed:false,synthetic:false,checks:[],pageErrors:[],httpErrors:[],blockedWrites:[],historyRequests:[],limitations:'Read-only review, not account/research/trading activation, native zoom, hosted acceptance or complete node capture.'};
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',route=>{
  const r=route.request(),u=new URL(r.url());
  if(r.method()==='POST'&&u.pathname==='/api/preferences/theme')return route.fulfill({status:200,contentType:'application/json',body:'{"theme":"dark"}'});
  if(!['GET','HEAD','OPTIONS'].includes(r.method())&&u.pathname!='/api/diagnostics/events'){
   report.blockedWrites.push({method:r.method(),path:u.pathname});return route.abort();
  }
  return route.continue();
 });
 const page=await context.newPage();
 const starts=new Map();
 page.on('pageerror',e=>report.pageErrors.push(e.message));
 page.on('request',r=>starts.set(r,Date.now()));
 page.on('response',r=>{const u=new URL(r.url());if(r.status()>=400)report.httpErrors.push({path:u.pathname,status:r.status()});if(u.pathname.includes('/price-history/'))report.historyRequests.push({path:u.pathname,scope:u.searchParams.get('query_key'),status:r.status(),ms:Date.now()-starts.get(r.request())});});
 const spotVisible=async selector=>page.locator(selector).first().evaluate(e=>{
  const a=e.getBoundingClientRect(),s=e.querySelector('.trin-spot-chip')?.getBoundingClientRect(),h=e.querySelector('thead')?.getBoundingClientRect();
  return !!s&&s.top>=(h?.bottom || a.top)-1&&s.bottom<=a.bottom+1;
 });
 try {
  for(const desk of ['heatseeker','trinity']){
   const start=Date.now();
   await page.goto('http://127.0.0.1:3000/?page='+desk,{waitUntil:'domcontentloaded'});
   const bundle=new URL(await page.locator('script[src*="main."]').getAttribute('src'),page.url()).pathname.split('/').pop();
   if(report.bundle)assert.equal(report.bundle,bundle);else report.bundle=bundle;
   const selector=desk==='heatseeker'?'.skylit-options-study .skylit-heatmap-container':'.triad-pair .skylit-heatmap-container';
   await page.locator(selector+' .trin-cell[tabindex="0"]').first().waitFor({timeout:45000});
   const mapMs=Date.now()-start;
   if(desk==='heatseeker'){
    await page.waitForFunction(()=>Number(document.querySelector('[data-testid="recorded-price-chart"]')?.dataset.candles)>0,null,{timeout:45000});
    report.chartMs=Date.now()-start;
    report.priceCandles=await page.getByTestId('recorded-price-chart').getAttribute('data-candles');
   }
   await page.locator(selector).first().scrollIntoViewIfNeeded();
   assert.equal(await spotVisible(selector),true,desk+' initially hides the spot row');
   if(desk==='trinity'){
    const grids=page.locator(selector);
    assert.equal(await grids.count(),2,'Adjusted pane unavailable; inspect data state instead of substituting Raw');
    const axes=await grids.evaluateAll(es=>es.map(e=>[...e.querySelectorAll('.trin-row')].map(r=>r.dataset.strike)));
    assert.deepEqual(axes[0],axes[1]);
    await grids.first().evaluate(e=>{e.scrollTop=Math.min(e.scrollTop+54,e.scrollHeight-e.clientHeight);e.dispatchEvent(new Event('scroll'));});
    await page.waitForFunction(()=>{const es=document.querySelectorAll('.triad-pair .skylit-heatmap-container');return Math.abs(es[0].scrollTop-es[1].scrollTop)<1;});
    await page.locator('[data-testid="triad-pane-raw"]').getByRole('button',{name:'Center on price'}).click();
    assert.equal(await spotVisible(selector),true);
   }
   const chip=page.locator(selector+' .trin-row:has(.trin-spot-chip) .trin-cell[tabindex="0"]').first();
   await chip.click();
   let dialog=page.getByRole('dialog',{name:desk==='heatseeker'?'Selected level inspector':'Contract review'});
   if(desk==='trinity')await page.getByTestId('triad-contracts-btn').click();
   else if(await dialog.count()===0)await page.getByRole('button',{name:'Review',exact:true}).click();
   await dialog.waitFor();
   assert.match(await dialog.getByRole('group',{name:'Selected reading'}).innerText(),/SPY/);
   const tabs=[];
   for(const name of ['Wall','Contract','Flow','Public agent']){
    const now=Date.now();await dialog.getByRole('tab',{name,exact:true}).click();
    await dialog.getByRole('tabpanel',{name,exact:true}).waitFor();
    assert.equal(await dialog.getByRole('tabpanel').count(),1);tabs.push({name,ms:Date.now()-now});
    if(name==='Contract'){
     await dialog.getByLabel('Option type',{exact:true}).selectOption('call');
     const input=dialog.getByLabel('Exact strike',{exact:true});
     assert.ok(await input.inputValue());
     const geometry=await input.evaluate(e=>{const a=e.getBoundingClientRect(),p=e.closest('[role="tabpanel"]').getBoundingClientRect();return a.left>=p.left-1&&a.right<=p.right+1;});
     assert.ok(geometry,'Exact-contract input clipped by review panel');
    }
   }
   await dialog.getByRole('tab',{name:'Contract',exact:true}).click();
   assert.equal(await dialog.getByLabel('Option type',{exact:true}).inputValue(),'call','Tab switches discarded the selection');
   await dialog.getByRole('tab',{name:'Wall',exact:true}).click();
   const geometry=await page.evaluate(()=>{
    const a=document.querySelector('.skylit-drawer,.triad-drawer').getBoundingClientRect();
    const m=document.querySelector('.skylit-heatmap-area,.triad-review-analysis').getBoundingClientRect();
    return {inspectorLeft:a.left,mapRight:m.right,bodyWidth:document.body.scrollWidth,viewport:innerWidth};
   });
   assert.ok(geometry.mapRight<=geometry.inspectorLeft+1,'Desktop inspector covers the map');
   assert.ok(geometry.bodyWidth<=geometry.viewport+2,'Document overflow');
   await page.screenshot({path:path.join(OUTPUT,desk+'-review.png'),fullPage:true});
   report.checks.push({desk,viewport:1440,mapMs,initialSpotVisible:true,sharedAxesAndScroll:desk==='trinity',tabs,geometry});
   for(const width of [1280,768,390]){
    await page.setViewportSize({width,height:800});
    await dialog.getByRole('tab',{name:'Contract',exact:true}).click();
    const input=dialog.getByLabel('Exact strike',{exact:true});
    await input.scrollIntoViewIfNeeded();
    const bounds=await input.boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=width+1,'Input outside narrow viewport');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'Horizontal page overflow at '+width);
    await page.screenshot({path:path.join(OUTPUT,desk+'-'+width+'.png'),fullPage:true});
    report.checks.push({desk,viewport:width,contractInputsReachable:true});
   }
   await page.keyboard.press('Escape');assert.equal(await dialog.count(),0);
   await page.setViewportSize({width:1440,height:1000});
  }
  assert.equal(report.pageErrors.length,0);assert.equal(report.blockedWrites.length,0);
  assert.equal(report.httpErrors.length,0,'HTTP read failures require diagnosis');
  report.passed=true;
 } catch(error){report.failure=String(error);await page.screenshot({path:path.join(OUTPUT,'failure.png'),fullPage:true});throw error;}
 finally{fs.writeFileSync(path.join(OUTPUT,'browser.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
