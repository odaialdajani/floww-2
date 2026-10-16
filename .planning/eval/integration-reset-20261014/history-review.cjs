const path=require('path');
const fs=require('fs');
const assert=require('assert/strict');
const {chromium}=require(path.resolve(__dirname,'../../../frontend/node_modules/playwright'));

(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const receipt={passed:false,synthetic:false,backendReloadAuthorized:true,errors:[],blocked:[]};
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await page.route('**/*',route=>{
   const r=route.request(),pathname=new URL(r.url()).pathname;
   if(r.method()==='POST'&&pathname==='/api/preferences/theme')return route.fulfill({status:200,contentType:'application/json',body:'{"theme":"dark"}'});
   if(!['GET','HEAD','OPTIONS'].includes(r.method())&&pathname!=='/api/diagnostics/events'){
    receipt.blocked.push({method:r.method(),path:pathname});
    return route.abort();
   }
   return route.continue();
  });
  page.on('pageerror',e=>receipt.errors.push(e.message));
  await page.goto('http://127.0.0.1:3000/?page=heatseeker',{waitUntil:'domcontentloaded'});
  receipt.bundle=new URL(await page.locator('script[src*="main."]').getAttribute('src'),page.url()).pathname.split('/').pop();
  await page.waitForFunction(()=>Number(document.querySelector('[data-testid="recorded-price-chart"]')?.dataset.candles)>0,null,{timeout:45000});
  await page.getByText(/No saved readings match the map scope/).waitFor();
  await page.getByRole('button',{name:'Chart tools',exact:true}).click();
  const follow=page.getByRole('checkbox',{name:'Follow map scope'});
  assert.equal(await follow.isChecked(),true);
  const responsePromise=page.waitForResponse(response=>{
   const u=new URL(response.url());
   return u.pathname==='/api/heatseeker/price-history/SPY'&&!u.searchParams.has('query_key');
  });
  await follow.uncheck();
  await page.getByText(/Saved-view review.*not the current map scope/).waitFor();
  const response=await responsePromise;
  assert.equal(response.status(),200);
  const data=await response.json();
  assert.ok(data.scopes.includes(data.query_key),'Default saved view is not an available stored scope');
  assert.ok(data.candles_with_recorded_nodes>0,'Saved view has no eligible observed nodes');
  await page.waitForFunction(()=>document.querySelectorAll('[data-testid="saved-node-line"]').length>0);
  receipt.availableSavedViews=data.scopes.length;
  receipt.selectedSavedView={value:data.query_key,mode:'latest recorded scope in selected period'};
  receipt.candles=data.candles;
  receipt.candlesWithRecordedNodes=data.candles_with_recorded_nodes;
  receipt.drawnSavedLines=await page.getByTestId('saved-node-line').count();
  receipt.backendDiagnosticsLoaded=Object.hasOwn(data,'price_failure');
  receipt.noScopeSubstitution=data.scopes.includes(data.query_key);
  await page.screenshot({path:path.join(__dirname,'history-saved-view.png'),fullPage:true});
  assert.equal(receipt.errors.length,0);
  assert.equal(receipt.blocked.length,0);
  receipt.passed=true;
 }catch(error){receipt.failure=String(error);throw error;}
 finally{fs.writeFileSync(path.join(__dirname,'history-review.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt,null,2));await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
