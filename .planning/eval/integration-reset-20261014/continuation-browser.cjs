const path = require('path');
const fs = require('fs');
const assert = require('assert/strict');
const {chromium} = require(path.resolve(__dirname,'../../../frontend/node_modules/playwright'));
const scratch = __dirname;

(async () => {
  const browser = await chromium.launch({channel:'chrome',headless:true});
  const receipt = {passed:false,routeSmoke:[],syntheticChart:{synthetic:true},blockedMutations:[],suppressedPreferenceWrites:0,pageErrors:[]};
  const routes = [['flowseeker-pro','Screener'],['heatseeker','Stock chart'],['trinity','Market view'],['skylit','Options map'],['steal-three','Extra studies'],['portfolio','Portfolio'],['journal','Journal'],['public','Broker']];
  const guard = async route => {
    const req = route.request();
    if (req.method()==='POST' && new URL(req.url()).pathname==='/api/preferences/theme') {
      receipt.suppressedPreferenceWrites++;
      return route.fulfill({status:200,contentType:'application/json',body:'{"theme":"dark"}'});
    }
    if (!['GET','HEAD','OPTIONS'].includes(req.method()) && new URL(req.url()).pathname !== '/api/diagnostics/events') {
      receipt.blockedMutations.push({method:req.method(),path:new URL(req.url()).pathname});
      return route.fulfill({status:403,contentType:'application/json',body:'{"detail":"Mutation blocked by read-only review"}'});
    }
    return route.continue();
  };
  try {
    const served = await fetch('http://127.0.0.1:3000/');
    assert.equal(served.status,200);
    receipt.bundle = (await served.text()).match(/main\.[a-f0-9]+\.js/)[0];
    const history = await (await fetch('http://127.0.0.1:8002/api/heatseeker/price-history/SPY?days=5&interval_minutes=30')).json();
    const recorder = await (await fetch('http://127.0.0.1:8002/api/solstice/recorder_health')).json();
    receipt.readChecks = {ticker:history.ticker,candles:history.candles,candlesWithRecordedNodes:history.candles_with_recorded_nodes,nodeStatus:history.node_status,recording:history.recording,queryKey:history.query_key,lastCandleAt:history.last_candle_at,receivedAt:history.prices_received_at,backgroundCapture:recorder.background_capture,captureWorker:recorder.capture?.worker_state};
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    await context.route('**/*',guard);
    for (const [id,label] of routes) {
      const page = await context.newPage(), failures=[];
      page.on('pageerror',error=>receipt.pageErrors.push({route:id,error:error.message}));
      page.on('response',response=>{if(response.status()>=400)failures.push({status:response.status(),path:new URL(response.url()).pathname});});
      const started = Date.now();
      await page.goto('http://127.0.0.1:3000/?page='+id,{waitUntil:'domcontentloaded'});
      await page.locator('main.floww-workspace-main').waitFor({timeout:30000});
      await page.waitForFunction(()=>document.querySelector('main')?.innerText.length>100,null,{timeout:30000});
      await page.waitForTimeout(1500);
      const text = await page.locator('main.floww-workspace-main').innerText();
      assert.ok(text.startsWith(label),'Wrong workspace breadcrumb: '+id);
      assert.doesNotMatch(text,/This section couldn't render|Something went wrong/);
      const limitations = [...new Set(text.split('\n').map(line=>line.trim()).filter(line=>/unavailable|not connected|no .*saved|not configured|loading|no .*recorded|no matching|not checked/i.test(line)))];
      receipt.routeSmoke.push({route:id,label,renderMs:Date.now()-started,rendered:true,httpFailures:failures,limitations:limitations.slice(0,15)});
      await page.close();
    }
    await context.close();

    // Deliberately synthetic transport, separate browser context. This proves
    // compiled rendering/replay boundaries, not live option-price availability.
    const synthetic = await browser.newContext({viewport:{width:1440,height:1000}});
    await synthetic.route('**/*',guard);
    const frames = [0,1,2].map(i=>({time:`2026-10-06T13:${30+i}:00Z`,open:100,high:102,low:99,close:101,volume:[10,null,0][i],nodes:[]}));
    const symbol = 'SPY261017C00650000';
    await synthetic.route('**/api/heatseeker/price-history/SPY*',route=>{
      const selected = new URL(route.request().url()).searchParams.has('contract_symbol');
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ticker:'SPY',frames,price_status:'available',node_status:'available',candles_with_recorded_nodes:0,contract_symbol:selected?symbol:null,contract_status:selected?'available':'not_requested',contract_bars:selected?[{t:frames[0].time,c:5},{t:frames[2].time,c:999}]:[]})});
    });
    const page = await synthetic.newPage();
    page.on('pageerror',error=>receipt.pageErrors.push({route:'synthetic-chart',error:error.message}));
    await page.goto('http://127.0.0.1:3000/?page=heatseeker',{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelector('[data-testid="recorded-price-chart"]')?.dataset.candles==='3',null,{timeout:30000});
    assert.equal(await page.getByTestId('volume-bar').count(),2);
    assert.match(await page.getByTestId('volume-pane').textContent(),/Volume unavailable for 1 of 3/);
    await page.getByRole('button',{name:'Chart tools',exact:true}).click();
    await page.getByLabel('Option contract symbol').fill(symbol);
    await page.getByRole('button',{name:'Load contract',exact:true}).click();
    const pane = page.getByTestId('contract-premium-pane');
    await pane.waitFor();
    assert.match(await pane.innerText(),/2\/3 visible candles matched/);
    assert.equal(await pane.locator('circle[data-testid="contract-premium"]').count(),2);
    assert.equal(await pane.locator('polyline').count(),0,'missing premium was bridged');
    const slider = page.getByRole('slider',{name:'Replay position'});
    await slider.focus();
    await page.keyboard.press('Home');
    await page.waitForFunction(()=>document.querySelector('[data-testid="recorded-price-chart"]')?.dataset.candles==='1');
    assert.match(await pane.innerText(),/Range \$5.00–\$5.00/);
    assert.doesNotMatch(await pane.innerText(),/999/);
    assert.match(await pane.innerText(),/1\/1 visible candles matched/);
    receipt.syntheticChart = {synthetic:true,passed:true,unknownVolumeKeptGap:true,sparsePremiumKeptGap:true,replayExcludedFuturePremium:true};
    await page.screenshot({path:path.join(scratch,'synthetic-chart.png'),fullPage:true});
    await synthetic.close();
    assert.equal(receipt.routeSmoke.length,8);
    assert.equal(receipt.pageErrors.length,0);
    assert.equal(receipt.blockedMutations.length,0,'Opening a route tried to mutate product state');
    receipt.passed = true;
  } catch(error) {
    receipt.failure=String(error);
    throw error;
  } finally {
    fs.writeFileSync(path.join(__dirname,'continuation-browser.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify(receipt,null,2));
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
