/* Finite compiled-bundle acceptance. All API/WebSocket traffic is fixture-only. */
const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const assert = require('assert');
const os = require('os');
const binding = require('./r14_source_binding.cjs');
const root = path.resolve(__dirname, '..');
const build = path.join(root, 'frontend/build');
const evidence = process.argv[4] ? path.resolve(process.argv[4]) : path.join(root, 'docs/solstice/r14/evidence');
const fixturePath = path.join(root, 'docs/solstice/r14/evidence/vertical-fixture.json');
const fixture = JSON.parse(fs.readFileSync(fixturePath));
const playwright = require(process.argv[2]);
const executablePath = process.argv[3];
const python = process.argv[5];
assert(python, 'Provide the verified working interpreter for fixture-only admission');
let lastTurn = null;
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const artifact = JSON.parse(fs.readFileSync(path.join(build, 'asset-manifest.json')));
const bundleHashes = Object.fromEntries(Object.entries(artifact.files).filter(([k]) => /\.(js|css)$/.test(k)).map(([k,v]) => [k, sha(fs.readFileSync(path.join(build, v.replace(/^\//,''))))]));
const buildReceipt = JSON.parse(fs.readFileSync(path.join(build,'solstice-build-receipt.json')));
assert.deepStrictEqual(buildReceipt.sourceHashes,binding.sourceHashes(),'Source differs from the compiled build');
assert.deepStrictEqual(buildReceipt.bundleHashes,bundleHashes,'Bundle differs from build receipt');
const receipt = { zoomMethod:'Native Chromium page zoom via chrome.tabs.setZoom; not CSS/pinch emulation', buildSourceCommit:buildReceipt.sourceCommit, sourceHashes:binding.sourceHashes(), servedBundleHashes:{}, sourceCommit: execFileSync('git', ['--no-pager','rev-parse','HEAD'], {cwd:root,encoding:'utf8'}).trim(),
  fixtureHash: sha(fs.readFileSync(fixturePath)), bundleHashes, fixtureOnly: true,
  researchTransport:'Fixture HTTP with actual record-only ResearchReads/deterministic_answer subprocess; no lifespan/provider/model/durable save', researchTraces: [], externalRequestsBlocked: [], pageErrors: [], warnings: [], viewports: [], resizeTrace: [], keyboard: [], screenshots: [] };
const server = http.createServer((req,res) => {
  const pathname = new URL(req.url,'http://127.0.0.1').pathname;
  const candidate = path.join(build, pathname === '/' ? 'index.html' : pathname);
  const file = candidate.startsWith(build) && fs.existsSync(candidate) && fs.statSync(candidate).isFile() ? candidate : path.join(build,'index.html');
  res.setHeader('Content-Type', ({'.js':'application/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png'})[path.extname(file)] || 'text/html');
  res.end(fs.readFileSync(file));
});
function apiBody(url) {
  const p = url.pathname;
  if (/\/heatmap\/SPY|\/data\/SPY/.test(p)) return url.searchParams.get('expiry_scope')==='next' ? fixture.next_display : fixture.display;
  if (/\/heatmap\/QQQ|\/data\/QQQ/.test(p)) return fixture.secondary_display;
  if (/\/heatmap\/|\/data\//.test(p)) return {ticker:p.split('/').pop(),data_source:'error',status:'unavailable',reason:'FIXTURE_HAS_NO_SYMBOL',strikes:[],grid:{}};
  if (/\/spot\/SPY/.test(p)) return {ticker:'SPY',spot:fixture.display.spot,asof:fixture.display.asof};
  if (/\/solstice\/replay\//.test(p)) return fixture.replay;
  if (/\/solstice\/SPY\/contract/.test(p)) return fixture.contract;
  if (/\/solstice\/scan/.test(p)) return {status:'not-scanned',leaderboard:[],availability:[],rank_method:'solstice-rank.v1'};
  if (/\/tickers/.test(p)) return {popular:['SPY','QQQ'],default:['SPY','QQQ'],trinity:['SPY','QQQ','^SPX'],tickers:['SPY','QQQ']};
  if (/\/decisions/.test(p)) return {decisions:fixture.decisions};
  if (/\/snapshots|\/manifest\//.test(p)) return {snapshots:[{id:fixture.display.snapshotId,snapshot_id:fixture.display.snapshotId,asof_ts:fixture.display.asof}]};
  if (p === '/api/agent/session') return {status:'fixture-only',persistent:false};
  if (/\/agent\/turn\//.test(p)) return {turn:lastTurn};
  if (/\/movers/.test(p)) return {status:'empty',movers:[],rows:[],schema_version:'movers.v2'};
  if (/\/price-history/.test(p)) return {frames:[],status:'unavailable',reason:'NO_FIXTURE_PRICE_PATH'};
  return {status:'unavailable',reason:'NO_FIXTURE_CAPABILITY',rows:[],alerts:[],history:[],contracts:[],items:[]};
}
(async () => {
  let browser;
  const temp = fs.mkdtempSync(path.join(os.tmpdir(),'zed-r14-browser-'));
  const extension = path.join(temp,'zoom');
  fs.mkdirSync(extension);
  fs.writeFileSync(path.join(extension,'manifest.json'),JSON.stringify({manifest_version:3,name:'Offline zoom acceptance',version:'1.0',permissions:['tabs'],background:{service_worker:'worker.js'}}));
  fs.writeFileSync(path.join(extension,'worker.js'),'chrome.runtime.onInstalled.addListener(()=>{});');
  try {
    await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
    const origin = `http://127.0.0.1:${server.address().port}`;
    for (const [key,file] of Object.entries(artifact.files).filter(([k])=>/\.(js|css)$/.test(k))) {
      const response = await fetch(origin+'/'+file.replace(/^\//,''));
      receipt.servedBundleHashes[key] = sha(Buffer.from(await response.arrayBuffer()));
      assert.strictEqual(receipt.servedBundleHashes[key],bundleHashes[key],'Served bundle mismatch: '+key);
    }
    browser = await playwright.chromium.launchPersistentContext(path.join(temp,'profile'),{headless:true,executablePath,viewport:{width:1440,height:1000},args:['--disable-extensions-except='+extension,'--load-extension='+extension]});
    const context = browser;
    receipt.browser = context.browser().version();
    const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker',{timeout:15000});
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/agent/ask') {
        const body = route.request().postDataJSON();
        lastTurn = JSON.parse(execFileSync(python,[path.join(root,'scripts/r14_answer.py'),fixturePath],{cwd:root,input:JSON.stringify(body),encoding:'utf8',timeout:25000}));
        receipt.researchTraces.push({family:body.screen.selectedContract?'contract':body.screen.overlayMetric==='window'?'window':body.screen.metric,
          selector:body.screen,modelStatus:lastTurn.answer.model_status,ledger:lastTurn.answer.facts,gaps:lastTurn.answer.gaps});
        return route.fulfill({json:{turn_id:lastTurn.turn_id}});
      }
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
      receipt.viewports.push({name,requestedWidth:width,cssZoom:zoom,...metrics});
      const filename = `${name}-${width}${zoom!==1?'-zoom200':''}.png`;
      if (name === 'solstice-native200') {
        // Native zoom uses browser DIP for capture but CSS pixels for layout.
        // Playwright fullPage clips to the smaller CSS viewport; capture the
        // actual widget instead, without changing zoom or emulating scale.
        const cdp = await context.newCDPSession(page);
        const image = await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false,fromSurface:true});
        fs.writeFileSync(path.join(evidence,filename),Buffer.from(image.data,'base64'));
        await cdp.detach();
      } else await page.screenshot({path:path.join(evidence,filename),fullPage:true});
      receipt.screenshots.push({file:filename,sha256:sha(fs.readFileSync(path.join(evidence,filename)))});
      assert(metrics.grids.some(g=>g.width>100&&g.height>100),`${name}: readable grid missing`);
    };
    for(const width of [1920,1440,1024,768,640,390]) await capture('solstice-focus',width);
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
    await page.setViewportSize({width:768,height:1000});
    await page.getByTestId('skylit-rawdelta-toggle').click();
    const rawPane = page.getByTestId('skylit-pane-gex');
    const adjustedPane = page.getByTestId('skylit-pane-delta');
    await capture('solstice-rawdelta',768);
    const targetCell = adjustedPane.getByRole('gridcell',{name:/^100 by/}).first();
    receipt.compareGeometry = await targetCell.evaluate(e=>{const r=e.getBoundingClientRect(); return {cell:r.toJSON(),viewport:{width:innerWidth,height:innerHeight},hit:document.elementFromPoint(Math.min(innerWidth-1,r.x+r.width/2),Math.min(innerHeight-1,r.y+r.height/2))?.className};});
    console.log('Compare geometry: '+JSON.stringify(receipt.compareGeometry));
    await targetCell.click({timeout:10000});
    assert.strictEqual(await rawPane.getByRole('gridcell',{selected:true}).count(),1,'Raw pane must share selection');
    assert.strictEqual(await adjustedPane.getByRole('gridcell',{selected:true}).count(),1,'Adjusted pane must share selection');
    const selected = await Promise.all([rawPane,adjustedPane].map(p=>p.getByRole('gridcell',{selected:true}).getAttribute('aria-label')));
    assert(selected.every(s=>s.startsWith('100 by')),'Selected strike differs between panes');
    await page.keyboard.press('Escape');
    await page.getByTestId('skylit-inspector-drawer').waitFor({state:'hidden'});
    const rawScroll = rawPane.locator('.skylit-heatmap-container');
    const adjustedScroll = adjustedPane.locator('.skylit-heatmap-container');
    await rawScroll.evaluate(e=>{e.scrollLeft=30;e.dispatchEvent(new Event('scroll'));});
    await page.waitForTimeout(100);
    const linked = await Promise.all([rawScroll,adjustedScroll].map(p=>p.evaluate(e=>({left:e.scrollLeft,top:e.scrollTop}))));
    assert(linked[0].left>0 && Math.abs(linked[0].left-linked[1].left)<=1,'Linked horizontal scroll lost alignment');
    assert.strictEqual(await page.getByTestId('skylit-follow-spot-toggle').getAttribute('aria-pressed'),'false','Manual scroll must pause Follow');
    await page.getByTestId('skylit-follow-spot-toggle').click();
    assert.strictEqual(await page.getByTestId('skylit-follow-spot-toggle').getAttribute('aria-pressed'),'true','Follow resumes only explicitly');
    receipt.linkedCompare = {status:'passed',selection:selected,scroll:linked,followPauseResume:true};
    await page.keyboard.press('Escape');
    await page.getByTestId('skylit-rawdelta-toggle').click();
    await page.setViewportSize({width:1440,height:1000});
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
    for(const width of [1440,768,640,390]) await capture('triad',width);
    await page.getByLabel('Triad expiry scope').selectOption('next');
    await page.getByTestId('triad-signed-profile').waitFor();
    assert.strictEqual(await page.getByTestId('triad-pane-raw').getByRole('columnheader').count(),2,'Next listed must render one actual expiry plus strike rail');
    receipt.keyboard.push('Next listed renders the bounded producer fixture; no 0DTE substitution');
    await goto('heatseeker');
    await page.getByLabel('Canvas layout').waitFor();
    await page.setViewportSize({width:1440,height:1000});
    // New R14 acceptance: existing review/context/drawer, actual record-only
    // admission/answer modules behind fixture HTTP (not a live/durable service).
    const askCurrent = async family => {
      await page.getByTestId('ask-lodestar-btn').first().click();
      await page.getByTestId('ask-lodestar-q-0').first().click();
      const dialog=page.getByRole('dialog',{name:'Lodestar research'});
      await dialog.getByRole('article',{name:'Research answer for SPY'}).waitFor();
      const trace=receipt.researchTraces[receipt.researchTraces.length-1];
      assert.strictEqual(trace.family,family,'Drawer used a different context family');
      assert(trace.ledger.length>0,`No admitted server facts for ${family}: ${trace.gaps.join(';')}`);
      assert.strictEqual(trace.selector.snapshotId,fixture.display.snapshotId,'Owning observation mismatch');
      assert.deepStrictEqual(trace.selector.mapQuery,fixture.display.map_query,'Query mismatch');
      await dialog.getByText(/^Evidence \(/).click();
      await dialog.getByText(trace.ledger[0].metric,{exact:true}).waitFor();
      const filename=`solstice-${family}-lodestar-1440.png`;
      await page.screenshot({path:path.join(evidence,filename),fullPage:true});
      receipt.screenshots.push({file:filename,sha256:sha(fs.readFileSync(path.join(evidence,filename)))});
      await dialog.getByRole('button',{name:'Close',exact:true}).click();
    };
    await page.getByRole('gridcell',{name:/^100 by/}).first().click();
    await page.getByLabel('Exact strike',{exact:true}).fill('100');
    await page.getByLabel('Listed expiry',{exact:true}).selectOption(fixture.contract.matched_identity.expiry);
    await page.getByLabel('Option type',{exact:true}).selectOption(fixture.contract.matched_identity.type);
    await page.getByRole('button',{name:'Resolve exact contract',exact:true}).click();
    await page.getByTestId('exact-contract-result').waitFor();
    assert((await page.getByTestId('exact-contract-result').textContent()).includes('synthetic_contract_spec'),'Multiplier source not visible with AI closed');
    await askCurrent('contract');
    await page.keyboard.press('Escape');
    await page.getByLabel('GEX basis').selectOption('window');
    await page.getByRole('gridcell',{name:/^100 by/}).first().click();
    await askCurrent('window');
    const windowTrace=receipt.researchTraces[receipt.researchTraces.length-1];
    assert.strictEqual(windowTrace.selector.windowBaselineId,fixture.display.metrics.grids.window.comparison.previous_snapshot_id,'Baseline changed');
    await page.keyboard.press('Escape');
    await page.getByLabel('GEX basis').selectOption('raw');
    await page.getByRole('button',{name:'Replay',exact:true}).click();
    await page.getByTestId('solstice-replay-load').click();
    await page.getByTestId('solstice-replay-next').click();
    await page.getByTestId('solstice-replay-banner').waitFor();
    for(const metric of ['vex','charm']) {
      await page.getByRole('button',{name:metric==='vex'?'VEX':'Charm',exact:true}).click();
      await page.getByRole('gridcell',{name:/^100 by/}).first().click();
      await askCurrent(metric);
      const trace=receipt.researchTraces[receipt.researchTraces.length-1];
      assert.strictEqual(trace.selector.displayMode,'replay');
      assert.strictEqual(trace.selector.recordedMetricVersion,'metric-record.v1');
      assert.strictEqual(await page.getByTestId('skylit-trade-btn').isDisabled(),true,'Replay must not arm Trade');
      await page.keyboard.press('Escape');
    }
    await page.getByTestId('solstice-replay-exit').click();
    await page.getByRole('button',{name:'GEX',exact:true}).click();
    const beforeZoom = await page.evaluate(()=>({width:innerWidth,dpr:devicePixelRatio}));
    const tabId = await worker.evaluate(async url => (await chrome.tabs.query({})).find(t=>t.url?.startsWith(url)).id,origin);
    await worker.evaluate(async id => chrome.tabs.setZoom(id,2),tabId);
    await page.waitForTimeout(250);
    const nativeZoom = await worker.evaluate(async id => chrome.tabs.getZoom(id),tabId);
    const afterZoom = await page.evaluate(()=>({width:innerWidth,dpr:devicePixelRatio,cssZoom:getComputedStyle(document.body).zoom,visualScale:visualViewport.scale}));
    assert.strictEqual(nativeZoom,2,'Native zoom API must report 200%');
    assert(afterZoom.width<=beforeZoom.width*.51,'Native zoom must halve layout viewport width');
    assert.strictEqual(afterZoom.cssZoom,'1','CSS zoom is not native acceptance');
    assert.strictEqual(afterZoom.visualScale,1,'Pinch/page-scale emulation is not native acceptance');
    receipt.nativeZoom = {status:'passed',factor:nativeZoom,before:beforeZoom,after:afterZoom,method:'chrome.tabs.setZoom (browser-native page zoom; no UI-menu click claim)'};
    await page.getByRole('grid').first().evaluate(e=>e.scrollIntoView({block:'center'}));
    await page.waitForTimeout(100);
    const nativeAccess = await page.getByRole('grid').first().evaluate(e=>{
      const container=e.closest('.skylit-heatmap-container').getBoundingClientRect();
      const painted=[...e.querySelectorAll('[role="gridcell"]')].filter(cell=>{
        const r=cell.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;
        return x>=0&&x<innerWidth&&y>=0&&y<innerHeight&&cell.contains(document.elementFromPoint(x,y));
      }).length;
      return {container:container.toJSON(),table:e.getBoundingClientRect().toJSON(),viewport:{width:innerWidth,height:innerHeight},paintedCells:painted};
    });
    receipt.nativeZoom.matrixAccess={method:'native DOM container scrolling; CSS layout geometry and paint hit tests',...nativeAccess};
    assert(nativeAccess.container.x>=0 && nativeAccess.container.right<=nativeAccess.viewport.width+1,'Native zoom matrix scroll container must fit viewport');
    assert(nativeAccess.paintedCells>0,'Native zoom matrix must be painted and accessible, not merely mounted offscreen');
    await capture('solstice-native200',1440);
    await worker.evaluate(async id => chrome.tabs.setZoom(id,1),tabId);
    assert(receipt.pageErrors.length===0,`uncaught errors: ${receipt.pageErrors.join('; ')}`);
    assert(!receipt.warnings.some(w=>/ResizeObserver loop/.test(w.text)),'persistent ResizeObserver loop');
    receipt.status='passed_fixture_browser_checks';
    fs.writeFileSync(path.join(evidence,'browser-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
    console.log(JSON.stringify({status:receipt.status,viewports:receipt.viewports.length,resizeIterations:60,pageErrors:receipt.pageErrors.length,warnings:receipt.warnings.length,fixtureHash:receipt.fixtureHash}));
  } catch(e) {
    receipt.status='failed'; receipt.failure=e.message;
    fs.writeFileSync(path.join(evidence,'browser-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
    console.error(e.message); process.exitCode=1;
  } finally {if(browser) await browser.close(); await new Promise(resolve=>server.close(resolve)); fs.rmSync(temp,{recursive:true,force:true});}
})();
