const path = require('path');
const fs = require('fs');
const assert = require('assert/strict');
const repo = path.resolve(__dirname, '../../..');
const {chromium} = require(path.join(repo, 'frontend/node_modules/playwright'));

(async () => {
  const browser = await chromium.launch({channel:'chrome',headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const errors = [], blocked = [], requests = [], networkErrors = [], transportErrors = [], historyRequests = [];
  const receipt = {synthetic:false, checks:[], errors, blocked, networkErrors, transportErrors, historyRequests};
  const startedRequests = new Map();
  await context.route('**/*', async route => {
    const req = route.request();
    const pathname = new URL(req.url()).pathname;
    if (req.method() === 'POST' && pathname === '/api/preferences/theme') {
      return route.fulfill({status:200,contentType:'application/json',body:'{"theme":"dark"}'});
    }
    if (!['GET','HEAD','OPTIONS'].includes(req.method()) && pathname !== '/api/diagnostics/events') {
      blocked.push({method:req.method(),path:pathname});
      return route.abort();
    }
    return route.continue();
  });
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(e.message));
  page.on('requestfailed', r => {if(r.failure()?.errorText !== 'net::ERR_ABORTED') transportErrors.push({path:new URL(r.url()).pathname,error:r.failure()?.errorText});});
  page.on('response', r => {
    if(r.status() >= 400) networkErrors.push({status:r.status(),path:new URL(r.url()).pathname});
    const req=r.request(), url=new URL(req.url());
    if(url.pathname.includes('/price-history/') && startedRequests.has(req))
      historyRequests.push({scope:url.searchParams.get('query_key')||'latest',ms:Date.now()-startedRequests.get(req),status:r.status()});
  });
  page.on('request', req => {
    const pathname=new URL(req.url()).pathname;
    requests.push({method:req.method(),path:pathname});
    if(pathname.includes('/price-history/')) startedRequests.set(req,Date.now());
  });
  try {
    let started = Date.now();
    await page.goto('http://127.0.0.1:3000/?page=heatseeker', {waitUntil:'domcontentloaded'});
    receipt.bundle = new URL(await page.locator('script[src*="main."]').getAttribute('src'),page.url()).pathname.split('/').pop();
    const options = page.getByRole('region', {name:'SPY options desk'});
    await options.locator('[role=gridcell][tabindex="0"]').first().waitFor({timeout:45000});
    const renderMs = Date.now()-started;
    await page.waitForFunction(() => Number(document.querySelector('[data-testid="recorded-price-chart"]')?.dataset.candles) > 0, null, {timeout:45000});
    const chartReadyMs = Date.now()-started;
    const landmarks = options.locator('[aria-label="Raw OI landmarks"]').first();
    assert.match(await landmarks.innerText(), /Call wall/);
    assert.match(await landmarks.innerText(), /Put wall/);
    assert.match(await landmarks.innerText(), /Support watch/);
    assert.match(await landmarks.innerText(), /Resistance watch/);
    assert.match(await page.getByRole('region',{name:'Map levels separate from historical candles'}).innerText(), /not historical candle-time/);
    await options.locator('.trin-row:has(.heatmap-row-landmark) [role=gridcell][tabindex="0"]').first().click();
    const dialog = page.getByRole('dialog',{name:'Selected level inspector'});
    await dialog.waitFor();
    assert.equal(await dialog.getByRole('tab').count(),4);
    assert.equal(await dialog.getByRole('tabpanel').count(),1);
    const tabTimes = [];
    for (const name of ['Contract','Flow','Public agent','Wall']) {
      started = Date.now();
      await dialog.getByRole('tab',{name,exact:true}).click();
      await dialog.getByRole('tabpanel',{name,exact:true}).waitFor({state:'visible'});
      tabTimes.push({name,ms:Date.now()-started});
    }
    const geometry = await page.evaluate(() => {
      const grid = document.querySelector('.skylit-options-study .skylit-heatmap-area').getBoundingClientRect();
      const inspector = document.querySelector('.skylit-drawer').getBoundingClientRect();
      return {gridRight:grid.right,inspectorLeft:inspector.left,inspectorWidth:inspector.width};
    });
    assert.ok(geometry.gridRight <= geometry.inspectorLeft+1,'desktop inspector covers map');
    await page.screenshot({path:path.join(__dirname,'solstice.png'),fullPage:true});
    receipt.checks.push({desk:'Solstice',renderMs,chartReadyMs,tabTimes,geometry,landmarks:await landmarks.innerText(),candleCount:await page.locator('[data-testid="recorded-price-chart"]').first().getAttribute('data-candles')});
    await page.keyboard.press('Escape');
    assert.equal(await dialog.count(),0);
    await page.setViewportSize({width:1280,height:800});
    await options.locator('.trin-row:has(.heatmap-row-landmark) [role=gridcell][tabindex="0"]').first().click();
    await page.getByRole('button',{name:'Review',exact:true}).click();
    await page.getByRole('dialog',{name:'Selected level inspector'}).waitFor();
    receipt.checks.push({desk:'Solstice',viewport:1280,inspector:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.goto('http://127.0.0.1:3000/?page=trinity',{waitUntil:'domcontentloaded'});
    const scope = page.getByLabel('Triad expiry scope');
    await scope.waitFor({timeout:45000});
    await scope.selectOption('next');
    const wall = page.locator('[data-testid^="triad-wall-w_"]').first();
    await wall.waitFor({timeout:45000});
    await wall.click();
    await page.getByTestId('triad-contracts-btn').click();
    const triad = page.getByRole('dialog',{name:'Contract review'});
    await triad.waitFor();
    for (const name of ['Contract','Flow','Public agent','Wall']) {
      await triad.getByRole('tab',{name,exact:true}).click();
      await triad.getByRole('tabpanel',{name,exact:true}).waitFor({state:'visible'});
    }
    assert.equal(await triad.getByRole('tab').count(),4);
    const triadGeometry = await page.evaluate(() => {
      const sidebar=document.querySelector('aside[data-collapsed]').getBoundingClientRect();
      const main=document.querySelector('main.floww-workspace-main').getBoundingClientRect();
      return {scrollX:window.scrollX,sidebarRight:sidebar.right,mainLeft:main.left,bodyWidth:document.body.scrollWidth,viewport:innerWidth};
    });
    assert.equal(triadGeometry.scrollX,0,'Triad wall review horizontally scrolled the page');
    assert.ok(triadGeometry.mainLeft>=triadGeometry.sidebarRight,'Triad workspace is behind the sidebar');
    await page.screenshot({path:path.join(__dirname,'triad.png'),fullPage:true});
    receipt.checks.push({desk:'Triad',scope:'next',tabs:4,geometry:triadGeometry,landmarks:await page.locator('[aria-label="Raw OI landmarks"]').first().innerText()});
    await page.keyboard.press('Escape');
    assert.equal(await triad.count(),0);
    assert.equal(errors.length,0);
    assert.equal(networkErrors.length,0,'HTTP read failed');
    assert.equal(transportErrors.length,0,'Transport read failed');
    assert.equal(blocked.length,0,'a forbidden request was attempted');
    receipt.requestCounts = requests.reduce((a,r) => {const k=r.method+' '+r.path;a[k]=(a[k]||0)+1;return a;},{});
    receipt.passed = true;
  } catch (e) {
    receipt.passed = false;receipt.failure = String(e);
    await page.screenshot({path:path.join(__dirname,'browser-failure.png'),fullPage:true});
    throw e;
  } finally {
    fs.writeFileSync(path.join(__dirname,'browser.json'), JSON.stringify(receipt,null,2)+'\n');
    await browser.close();
    console.log(JSON.stringify(receipt,null,2));
  }
})().catch(e => {console.error(e);process.exitCode=1;});
