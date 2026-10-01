/* Finite compiled-bundle acceptance. All API/WebSocket traffic is fixture-only. */
const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const assert = require('assert');
const root = path.resolve(__dirname, '..');
const build = path.join(root, 'frontend/build');
const evidence = path.join(root, 'docs/solstice/r11/evidence');
const fixturePath = path.join(evidence, 'vertical-fixture.json');
const fixture = JSON.parse(fs.readFileSync(fixturePath));
const playwright = require(process.argv[2]);
const executablePath = process.argv[3];
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const artifact = JSON.parse(fs.readFileSync(path.join(build, 'asset-manifest.json')));
const bundleHashes = Object.fromEntries(Object.entries(artifact.files).filter(([k]) => /\.(js|css)$/.test(k)).map(([k,v]) => [k, sha(fs.readFileSync(path.join(build, v.replace(/^\//,''))))]));
const receipt = { zoomMethod:'CSS zoom simulation; actual browser UI zoom acceptance remains pending', sourceCommit: execFileSync('git', ['--no-pager','rev-parse','HEAD'], {cwd:root,encoding:'utf8'}).trim(),
  fixtureHash: sha(fs.readFileSync(fixturePath)), bundleHashes, fixtureOnly: true,
  externalRequestsBlocked: [], pageErrors: [], warnings: [], viewports: [], resizeTrace: [], keyboard: [], screenshots: [] };
const server = http.createServer((req,res) => {
  const pathname = new URL(req.url,'http://127.0.0.1').pathname;
  const candidate = path.join(build, pathname === '/' ? 'index.html' : pathname);
  const file = candidate.startsWith(build) && fs.existsSync(candidate) && fs.statSync(candidate).isFile() ? candidate : path.join(build,'index.html');
  res.setHeader('Content-Type', ({'.js':'application/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png'})[path.extname(file)] || 'text/html');
  res.end(fs.readFileSync(file));
});
function apiBody(url) {
  const p = url.pathname;
  if (/\/heatmap\/SPY|\/data\/SPY/.test(p)) return fixture.display;
  if (/\/heatmap\/QQQ|\/data\/QQQ/.test(p)) return fixture.secondary_display;
  if (/\/heatmap\/|\/data\//.test(p)) return {ticker:p.split('/').pop(),data_source:'error',status:'unavailable',reason:'FIXTURE_HAS_NO_SYMBOL',strikes:[],grid:{}};
  if (/\/spot\/SPY/.test(p)) return {ticker:'SPY',spot:fixture.display.spot,asof:fixture.display.asof};
  if (/\/solstice\/replay\//.test(p)) return fixture.replay;
  if (/\/solstice\/SPY\/contract/.test(p)) return fixture.contract;
  if (/\/solstice\/scan/.test(p)) return {status:'not-scanned',leaderboard:[],availability:[],rank_method:'solstice-rank.v1'};
  if (/\/tickers/.test(p)) return {popular:['SPY','QQQ'],default:['SPY','QQQ'],trinity:['SPY','QQQ','^SPX'],tickers:['SPY','QQQ']};
  if (/\/decisions/.test(p)) return {decisions:fixture.decisions};
  if (/\/snapshots/.test(p)) return {snapshots:[{snapshot_id:fixture.display.snapshotId,asof_ts:fixture.display.asof}]};
  if (/\/movers/.test(p)) return {status:'empty',movers:[],rows:[],schema_version:'movers.v2'};
  if (/\/price-history/.test(p)) return {frames:[],status:'unavailable',reason:'NO_FIXTURE_PRICE_PATH'};
  return {status:'unavailable',reason:'NO_FIXTURE_CAPABILITY',rows:[],alerts:[],history:[],contracts:[],items:[]};
}
(async () => {
  let browser;
  try {
    await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    browser = await playwright.chromium.launch({headless:true,executablePath});
    receipt.browser = browser.version();
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.pathname.startsWith('/api/')) return route.fulfill({json:apiBody(url)});
      if (url.origin === origin) return route.continue();
      receipt.externalRequestsBlocked.push({host:url.hostname,path:url.pathname});
      return route.abort();
    });
    if (context.routeWebSocket) await context.routeWebSocket('**/*', ws => ws.close());
    const page = await context.newPage();
    page.on('pageerror', e => receipt.pageErrors.push(e.message));
    page.on('console', m => {if (['warning','error'].includes(m.type())) receipt.warnings.push({type:m.type(),text:m.text()});});
    const goto = async tab => {await page.goto(`${origin}/?page=${tab}&ticker=SPY&view=skylit`); await page.waitForTimeout(500);};
    await goto('heatseeker');
    await page.getByLabel('Canvas layout').waitFor();
    const capture = async (name,width,zoom=1) => {
      await page.setViewportSize({width,height:1000});
      await page.evaluate(z => {document.body.style.zoom=String(z);},zoom);
      await page.waitForTimeout(100);
      const metrics = await page.evaluate(() => ({width:innerWidth,height:innerHeight,
        documentWidth:document.documentElement.scrollWidth,documentHeight:document.documentElement.scrollHeight,
        grids:[...document.querySelectorAll('[role="grid"]')].map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height})),
        toolbar:document.querySelector('[aria-label="Canvas controls"]')?.getBoundingClientRect().toJSON()}));
      receipt.viewports.push({name,width,zoom,...metrics});
      const filename = `${name}-${width}${zoom!==1?'-zoom200':''}.png`;
      await page.screenshot({path:path.join(evidence,filename),fullPage:true});
      receipt.screenshots.push({file:filename,sha256:sha(fs.readFileSync(path.join(evidence,filename)))});
      assert(metrics.grids.some(g=>g.width>100&&g.height>100),`${name}: readable grid missing`);
    };
    for(const width of [1920,1440,1024,768,390]) await capture('solstice-focus',width);
    await capture('solstice-focus',768,2);
    await page.evaluate(()=>{document.body.style.zoom='1';});
    await page.setViewportSize({width:1440,height:1000});
    await page.getByLabel('Canvas layout').selectOption('profile');
    await capture('solstice-profile',1440);
    const negative = page.locator('.trin-prof-bar.neg').first();
    const positive = page.locator('.trin-prof-bar.pos').first();
    assert(await negative.count()>0 && await positive.count()>0,'signed bars missing');
    const geometry = await page.evaluate(() => [...document.querySelectorAll('.trin-prof')].map(e=> {
      const z=e.querySelector('.trin-prof-zero')?.getBoundingClientRect();
      return [...e.querySelectorAll('.trin-prof-bar')].map(b=>{const r=b.getBoundingClientRect();return {negative:b.classList.contains('neg'),left:r.left,right:r.right,zero:z?.left};});
    }).flat());
    assert(geometry.every(b=>b.negative?b.right<=b.zero+1:b.left>=b.zero-1),'profile crosses wrong side of zero');
    receipt.profileGeometry = {bars:geometry.length,zeroSignAlignment:true};
    const firstCell=page.locator('[role="gridcell"]').first();
    await firstCell.focus(); await page.keyboard.press('ArrowDown');
    assert(await page.locator('[role="gridcell"]:focus').count()===1,'arrow focus escaped matrix');
    receipt.keyboard.push('ArrowDown retains matrix focus');
    await page.keyboard.press('Enter');
    await page.getByTestId('skylit-inspector-drawer').waitFor();
    receipt.keyboard.push('Enter selects and opens inspector');
    await page.keyboard.press('Escape');
    await page.getByTestId('skylit-inspector-drawer').waitFor({state:'hidden'});
    receipt.keyboard.push('Escape closes inspector');
    await page.getByLabel('Canvas layout').selectOption('multi');
    await capture('solstice-multi',1920);
    await page.getByLabel('Canvas layout').selectOption('symbols');
    await page.getByTestId('symbol-map-QQQ').getByRole('gridcell',{name:/^400 by/}).first().waitFor();
    await capture('solstice-symbols',1440);
    const qqqCell=page.getByTestId('symbol-map-QQQ').getByRole('gridcell',{name:/^400 by/}).first();
    await qqqCell.click();
    assert((await page.getByTestId('symbol-map-inspector').textContent()).includes('QQQ'),'active symbol inspector mismatch');
    receipt.keyboard.push('Independent QQQ axis/selection drives its own inspector');
    await page.getByLabel('Canvas layout').selectOption('calendar');
    await capture('solstice-calendar',1440);
    await page.getByLabel('Canvas layout').selectOption('focus');
    for(let i=0;i<60;i++) {
      const width=[1440,1024,800,640,390,768][i%6];
      await page.setViewportSize({width,height:900}); await page.waitForTimeout(35);
      receipt.resizeTrace.push(await page.evaluate(i=>({iteration:i,width:innerWidth,height:document.documentElement.scrollHeight,
        canvas:document.querySelector('[data-testid="skylit-heatmap-area"]')?.getBoundingClientRect().height}),i));
    }
    for(const width of [1440,1024,800,640,390,768]) {
      const heights=receipt.resizeTrace.filter(r=>r.width===width).map(r=>r.height);
      assert(Math.max(...heights)-Math.min(...heights)<=2,`height drift at ${width}`);
    }
    await goto('trinity'); await page.getByTestId('triad-signed-profile').waitFor();
    for(const width of [1440,768,390]) await capture('triad',width);
    assert(receipt.pageErrors.length===0,`uncaught errors: ${receipt.pageErrors.join('; ')}`);
    assert(!receipt.warnings.some(w=>/ResizeObserver loop/.test(w.text)),'persistent ResizeObserver loop');
    receipt.status='passed_fixture_browser_checks';
    fs.writeFileSync(path.join(evidence,'browser-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify({status:receipt.status,viewports:receipt.viewports.length,resizeIterations:60,pageErrors:receipt.pageErrors.length,warnings:receipt.warnings.length,fixtureHash:receipt.fixtureHash}));
  } catch(e) {
    receipt.status='failed'; receipt.failure=e.message;
    fs.writeFileSync(path.join(evidence,'browser-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
    console.error(e.message); process.exitCode=1;
  } finally {if(browser) await browser.close(); await new Promise(resolve=>server.close(resolve));}
})();
