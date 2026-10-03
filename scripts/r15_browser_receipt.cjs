/* Finite compiled full-app smoke. All APIs/WebSockets are fixture-only; no lifespan or model turn. */
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto'),assert=require('assert');
const {execFileSync}=require('child_process');
const {chromium}=require('../frontend/node_modules/playwright');
const root=path.resolve(__dirname,'..'),frontend=path.join(root,'frontend'),build=path.join(frontend,'build');
const evidence=path.join(root,'docs/solstice/integration/evidence');
const fixturePath=path.join(root,'docs/solstice/r14/evidence/vertical-fixture.json');
const fixture=JSON.parse(fs.readFileSync(fixturePath));
const coveragePath=path.join(frontend,'src/fixtures/integration/coverage-read.v1.json');
const coverage=JSON.parse(fs.readFileSync(coveragePath));
const lifecyclePath=path.join(frontend,'src/fixtures/integration/lifecycle-inventory.v1.json');
const lifecycle=JSON.parse(fs.readFileSync(lifecyclePath));
const python=process.argv[2],executablePath=process.argv[3];
assert(python && executablePath,'Provide verified interpreter and browser executable paths');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function sourceHashes(){
 const result={};
 const walk=dir=>{for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const name=path.join(dir,entry.name);if(entry.isDirectory())walk(name);else if(/\.(jsx?|css|json|mjs|py)$/.test(name))result[path.relative(root,name)]=hash(fs.readFileSync(name));}};
 walk(path.join(frontend,'src'));walk(path.join(root,'backend/services'));walk(path.join(root,'backend/routes'));
 for(const rel of ['frontend/package.json','frontend/package-lock.json','backend/server.py','scripts/r15_fixture_answer.py'])result[rel]=hash(fs.readFileSync(path.join(root,rel)));
 return result;
}
const source=sourceHashes();
execFileSync('npm',['run','build'],{cwd:frontend,env:{...process.env,CI:'true'},stdio:'inherit',timeout:180000});
assert.deepStrictEqual(sourceHashes(),source,'Owned source changed during compilation');
const manifest=JSON.parse(fs.readFileSync(path.join(build,'asset-manifest.json')));
const bundleHashes=Object.fromEntries(Object.entries(manifest.files).filter(([key])=>/\.(js|css)$/.test(key)).map(([key,value])=>[key,hash(fs.readFileSync(path.join(build,value.replace(/^\//,''))))]));
const receipt={version:'floww-browser-receipt.v1',fixtureOnly:true,sourceCommit:execFileSync('git',['--no-pager','rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),sourceHashes:source,bundleHashes,fixtureHash:hash(fs.readFileSync(fixturePath)),routes:[],viewports:[],screenshots:[],externalRequestsBlocked:[],forbiddenMutations:[],pageErrors:[],warnings:[],research:[],checks:[],coverageFixtureHash:hash(fs.readFileSync(coveragePath)),coverageReads:[],lifecycleFixtureHash:hash(fs.readFileSync(lifecyclePath)),lifecycleReads:[]};
let lastTurn=null,refuseComparison=false,overnightSessions=false,recoveryReview=false;
const controlledInventory={...lifecycle.inventory,...lifecycle.control_additions,protection:{...lifecycle.inventory.protection,...lifecycle.control_additions.protection}};
function body(url){
 const p=url.pathname;
 if(/\/heatmap\/SPY|\/data\/SPY/.test(p))return fixture.display;
 if(/\/heatmap\/QQQ|\/data\/QQQ/.test(p))return fixture.secondary_display;
 if(/\/heatmap\/|\/data\//.test(p))return {ticker:p.split('/').pop(),strikes:[],grid:{},quality:{state:'unavailable',setupEligible:false,reasonCodes:['NO_ENTITLED_FIXTURE']}};
 if(/\/solstice\/replay\//.test(p))return p.endsWith(fixture.baseline.snapshot.snapshot_id)?fixture.baseline:fixture.replay;
 if(/\/solstice\/SPY\/contract/.test(p))return fixture.contract;
 if(/\/manifest\//.test(p) && url.searchParams.get('day')==='2026-10-02')return {ticker:'SPY',day:'2026-10-02',snapshots:[],gaps:[{reason:'FIXTURE_INDEX_ONLY'}]};
  if(/\/manifest\//.test(p))return {ticker:'SPY',day:'2026-10-01',snapshots:[{id:fixture.baseline.snapshot.snapshot_id,asof:fixture.baseline.snapshot.asof_ts},{id:fixture.display.snapshotId,asof:fixture.display.asof}],gaps:[{reason:'FIXTURE_GAP'}]};
 if(p.endsWith('/recorder_health'))return {durable:false,backing:'memory',capture:{worker_state:'wired_off'}};
 if(p.endsWith('/price-paths/sessions'))return overnightSessions?coverage.overnight_sessions:{...coverage.sessions,days:[{...coverage.sessions.days[0],date:'2026-10-01',ny_date:'2026-10-01',first_asof:fixture.baseline.snapshot.asof_ts,last_asof:fixture.display.asof,latest_snapshot_id:fixture.display.snapshotId}]};
 if(p.endsWith('/price-paths/expiries'))return coverage.expiries;
 if(p.endsWith('/price-paths/comparable'))return {...(refuseComparison?coverage.refused_comparison:coverage.comparison),baseline_id:fixture.baseline.snapshot.snapshot_id,snapshot_id:fixture.display.snapshotId};
 if(p.includes('/attribute/'))return {ticker:'SPY',day:'2026-10-01',status:'ok',from:{id:fixture.baseline.snapshot.snapshot_id,asof:fixture.baseline.snapshot.asof_ts},to:{id:fixture.display.snapshotId,asof:fixture.display.asof},strike_deltas:[],walls_added:[],walls_removed:[],volume_deltas:[]};
 if(/\/solstice\/scan/.test(p))return {status:'not-scanned',leaderboard:[],availability:[],rank_method:'solstice-rank.v1'};
 if(p.includes('/tickers'))return {popular:['SPY','QQQ'],default:['SPY','QQQ'],trinity:['SPY','QQQ','^SPX'],tickers:['SPY','QQQ']};
 if(p.includes('/decisions'))return {decisions:fixture.decisions};
 if(p.includes('/movers'))return {status:'empty',movers:[],rows:[],schema_version:'movers.v2'};
 if(p.includes('/price-history'))return {frames:[],status:'unavailable',reason:'NO_FIXTURE_PRICE_PATH'};
 if(p==='/api/agent/session')return {status:'fixture-only',persistent:false};
 if(p.includes('/agent/turn/'))return lastTurn;
 if(p==='/api/agent/handoffs')return {handoffs:[]};
 if(p==='/api/public/execution-lifecycle/inventory')return recoveryReview?{...controlledInventory,intents:{n_known:0,n_open:0,n_unknown:0,open:[],unknown:[]}}:controlledInventory;
 if(p==='/api/public/account')return {ok:true,account_id:'FIXTURE-ACCOUNT'};
 if(p==='/api/public/portfolio')return {ok:true,account_id:'FIXTURE-ACCOUNT',cash:null,buying_power:null,portfolio_value:null,positions:[],position_count:0};
 if(p==='/api/public/orders')return {ok:true,orders:[{order_id:'fixture-partial',symbol:'SPY261008C00100000',side:'BUY',quantity:3,filled_quantity:1,status:'PARTIAL'}]};
 return {status:'unavailable',reason:'NO_FIXTURE_CAPABILITY',rows:[],alerts:[],history:[],contracts:[],items:[],positions:[],trades:[],orders:[]};
}
const server=http.createServer((req,res)=>{
 const pathname=new URL(req.url,'http://127.0.0.1').pathname;
 const candidate=path.resolve(build,'.'+pathname);
 const file=candidate.startsWith(build+path.sep) && fs.existsSync(candidate) && fs.statSync(candidate).isFile()?candidate:path.join(build,'index.html');
 res.setHeader('Content-Type',({'.js':'application/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml','.png':'image/png'})[path.extname(file)] || 'text/html');res.end(fs.readFileSync(file));
});
(async()=>{
 let context,temp;
 try{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`;
  for(const [key,value] of Object.entries(manifest.files).filter(([key])=>/\.(js|css)$/.test(key)))assert.strictEqual(hash(Buffer.from(await(await fetch(origin+value)).arrayBuffer())),bundleHashes[key],'Served bundle mismatch');
  temp=fs.mkdtempSync(path.join(evidence,'.browser-'));const extension=path.join(temp,'zoom');fs.mkdirSync(extension);
  fs.writeFileSync(path.join(extension,'manifest.json'),JSON.stringify({manifest_version:3,name:'Offline acceptance zoom',version:'1.0',permissions:['tabs'],background:{service_worker:'worker.js'}}));
  fs.writeFileSync(path.join(extension,'worker.js'),'chrome.runtime.onInstalled.addListener(()=>{});');
  context=await chromium.launchPersistentContext(path.join(temp,'profile'),{headless:true,executablePath,viewport:{width:1440,height:1000},args:['--disable-extensions-except='+extension,'--load-extension='+extension]});
  receipt.browser=context.browser().version();
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.pathname==='/api/agent/ask'){
    const asked=request.postDataJSON();lastTurn=JSON.parse(execFileSync(python,[path.join(root,'scripts/r15_fixture_answer.py'),fixturePath],{cwd:root,input:JSON.stringify(asked),encoding:'utf8',timeout:25000}));
    receipt.research.push({selector:asked.screen,turn_id:lastTurn.turn_id,fact_ids:lastTurn.answer.facts.map(f=>f.id),draft_id:lastTurn.answer.plan_draft.draft_id,executable:lastTurn.answer.plan_draft.executable});
    return route.fulfill({json:{turn_id:lastTurn.turn_id,status:'completed'}});
   }
   if(url.pathname.startsWith('/api/')){
    if(url.pathname==='/api/public/execution-lifecycle/inventory')receipt.lifecycleReads.push({path:url.pathname,method:request.method()});
    if(url.pathname.includes('/price-paths/'))receipt.coverageReads.push({path:url.pathname,query:url.search,method:request.method()});
    if(url.pathname==='/api/preferences/theme' && request.method()==='POST')return route.fulfill({json:{ok:true,fixture_only:true}});
    if(url.pathname.endsWith('/alerts/stream'))return route.fulfill({contentType:'text/event-stream',body:'retry: 300000\n: fixture no-feed\n\n'});
    if(request.method()!=='GET' && url.pathname!=='/api/agent/session'){
     receipt.forbiddenMutations.push({path:url.pathname,method:request.method()});return route.fulfill({status:403,json:{reason:'FIXTURE_MUTATION_REFUSED'}});
    }
    return route.fulfill({json:body(url)});
   }
   if(url.origin===origin)return route.continue();
   receipt.externalRequestsBlocked.push({host:url.hostname,path:url.pathname});return route.abort();
  });
  if(context.routeWebSocket)await context.routeWebSocket('**/*',ws=>ws.close());
  await context.addInitScript(()=>{localStorage.setItem('apw.sidebarCollapsed','true');localStorage.setItem('floww_app_key','FIXTURE-NOT-A-CREDENTIAL');});
  const page=await context.newPage();page.on('pageerror',error=>receipt.pageErrors.push(error.message));page.on('console',message=>{if(['warning','error'].includes(message.type()))receipt.warnings.push(message.text());});
  const navigate=async id=>{await page.goto(`${origin}/?page=${id}&evidence=keep#selection`);await page.waitForTimeout(500);};
  const capture=async(name,width)=>{
   await page.setViewportSize({width,height:1000});await page.waitForTimeout(150);
   const metrics=await page.evaluate(()=>({width:innerWidth,height:innerHeight,documentWidth:document.documentElement.scrollWidth,grids:[...document.querySelectorAll('[role="grid"]')].map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))}));
   receipt.viewports.push({name,requestedWidth:width,...metrics});
   const file=name+'-'+width+'.png';await page.screenshot({path:path.join(evidence,file),fullPage:true});receipt.screenshots.push({file,sha256:hash(fs.readFileSync(path.join(evidence,file)))});
   assert(metrics.grids.some(g=>g.width>100 && g.height>100),name+': readable matrix required');
  };
  for(const [id,label] of [['heatseeker','Solstice'],['trinity','Triad'],['skylit','Zenith'],['flowseeker-pro','Tidehunter Pro'],['steal-three','Steal Three'],['portfolio','Portfolio'],['journal','Journal'],['public','Broker']]){
   await navigate(id);await page.locator('nav').getByRole('button',{name:label,exact:true}).waitFor();assert.strictEqual(await page.locator('nav').getByRole('button',{name:label,exact:true}).getAttribute('aria-current'),'page');
   await page.reload();await page.waitForTimeout(200);assert(new URL(page.url()).searchParams.get('page')===id);receipt.routes.push({id,direct:true,refresh:true,active:true});
  }
  await navigate('public');assert.strictEqual(receipt.lifecycleReads.length,0,'Inventory must be on demand');await page.getByText('Local lifecycle inventory · read-only',{exact:true}).click();await page.getByRole('button',{name:'Read local lifecycle inventory',exact:true}).click();await page.getByRole('table',{name:'Process-local intent records'}).waitFor();const localReview=await page.getByRole('region',{name:'Local lifecycle review'}).textContent();assert(localReview.includes('Account attribution unavailable') && localReview.includes('UNKNOWN') && localReview.includes('Account policy installed · account-policy.v1') && localReview.includes('4 stored approvals · 1 revoked') && localReview.includes('not verified remote workflows'));assert(receipt.lifecycleReads.every(r=>r.method==='GET'));receipt.checks.push('on-demand local lifecycle inventory; installed policy and stored/revoked counts are not permission; GET only');await page.getByRole('table',{name:'Reported native protection support'}).waitFor();await page.screenshot({path:path.join(evidence,'public-inventory-1440.png'),fullPage:true});receipt.screenshots.push({file:'public-inventory-1440.png',sha256:hash(fs.readFileSync(path.join(evidence,'public-inventory-1440.png')))});recoveryReview=true;await page.getByRole('button',{name:'Read local lifecycle inventory',exact:true}).click();await page.getByText(/Recovery review required.*RECOVERY_REQUIRED/).waitFor();assert.strictEqual(await page.getByRole('table',{name:'Process-local intent records'}).count(),0);receipt.checks.push('empty local registry with stored rows discloses recovery review; no recovery or entry mutation');
  await navigate('heatseeker');await page.getByRole('grid').first().waitFor();
  await page.locator('nav').getByRole('button',{name:'Triad',exact:true}).click();await page.getByTestId('trinity-view').waitFor();
  assert(new URL(page.url()).searchParams.get('evidence')==='keep');assert(new URL(page.url()).hash==='#selection');
  await page.locator('nav').getByRole('button',{name:'Broker',exact:true}).click();await page.getByTestId('public-panel').waitFor();
  await page.goBack();await page.getByTestId('trinity-view').waitFor();await page.goBack();await page.getByLabel('Canvas layout').waitFor();await page.goForward();await page.getByTestId('trinity-view').waitFor();receipt.checks.push('browser back/forward + query/hash preservation');
  await navigate('heatseeker');for(const width of [1440,1280,390])await capture('solstice',width);
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('gridcell',{name:/^100 by/}).first().click();
  await page.getByTestId('skylit-drawer-close').click();const selected=await page.getByTestId('skylit-selected-cell').textContent();
  await page.getByTestId('skylit-expand-btn').click();await page.getByRole('dialog',{name:'Expanded heatmap grid'}).waitFor();await page.getByTestId('skylit-expand-close').click();assert.strictEqual(await page.getByTestId('skylit-selected-cell').textContent(),selected);receipt.checks.push('Expand restores selected strike and layout');
  await page.getByText('Listed 14–60 DTE coverage',{exact:true}).click();await page.getByRole('button',{name:'Read listed coverage',exact:true}).click();await page.getByRole('table',{name:'Listed expiry admission'}).waitFor();assert((await page.getByTestId('solstice-expiry-coverage').textContent()).includes('3 returned / 12 requested'));assert((await page.getByTestId('solstice-expiry-coverage').textContent()).includes('Upper edge not observed'));assert((await page.getByRole('table',{name:'Listed expiry admission'}).textContent()).includes('45 DTEADMITTEDOutside'));const projection=await page.getByTestId('solstice-expiry-projection').textContent();assert(projection.includes('Producer reports complete listing; exhaustive coverage unverified') && projection.includes('2026-11-16 · 45 DTE') && projection.includes('No analytical grid or owning display record'));await page.getByText('Listed 14–60 DTE coverage',{exact:true}).click();receipt.checks.push('count-limited exact admitted-expiry projection is listing-only; analytical range map unavailable; selection unchanged');
  await page.getByRole('button',{name:'Replay',exact:true}).click();overnightSessions=true;await page.getByRole('button',{name:'Stored sessions',exact:true}).click();await page.getByLabel('Recorded sessions').selectOption('2026-10-02');assert((await page.getByTestId('solstice-session-attribution').textContent()).includes('Stored day 2026-10-02 · NY date 2026-10-01'));const overnightRequest=page.waitForRequest(r=>r.url().includes('/manifest/SPY?day=2026-10-02'));await page.getByTestId('solstice-replay-load').click();await overnightRequest;receipt.checks.push('overnight attribution disclosed; manifest uses stored prefix, not normalized NY date (index-only fixture)');overnightSessions=false;await page.getByRole('button',{name:'Stored sessions',exact:true}).click();await page.getByLabel('Recorded sessions').selectOption('2026-10-01');assert.strictEqual(await page.getByLabel('Stored session date').inputValue(),'2026-10-01');await page.getByTestId('solstice-replay-load').click();
  await page.getByTestId('solstice-compare-btn').click();await page.getByTestId('solstice-compare-result').waitFor();refuseComparison=true;await page.getByTestId('solstice-compare-btn').click();await page.getByText(/Comparison unavailable.*SCOPE_MISMATCH/).waitFor();assert.strictEqual(await page.getByTestId('solstice-compare-result').count(),0);receipt.checks.push('stored day enumeration with declared NY attribution + dated load + admitted/refused exact record pair');
  await page.getByTestId('solstice-replay-play').click();await page.getByTestId('solstice-replay-banner').waitFor();await page.getByRole('button',{name:'Pause',exact:true}).click();await page.getByTestId('solstice-replay-scrub').fill('1');await page.getByTestId('solstice-replay-next').click();receipt.checks.push('recorded play/pause/scrub');
  await page.getByTestId('solstice-replay-prev').click();await page.getByTestId('solstice-replay-next').click();await page.getByTestId('solstice-replay-exit').click();receipt.checks.push('stored manifest, step both directions, deliberate Live exit');
  await page.getByRole('gridcell',{name:/^100 by/}).first().click();await page.getByRole('button',{name:'Review',exact:true}).click();await page.getByText('Exact contract review · read-only',{exact:true}).click();
  await page.getByLabel('Exact strike',{exact:true}).fill('100');await page.getByLabel('Listed expiry',{exact:true}).selectOption(fixture.contract.matched_identity.expiry);await page.getByLabel('Option type',{exact:true}).selectOption(fixture.contract.matched_identity.type);await page.getByRole('button',{name:'Resolve exact contract',exact:true}).click();await page.getByTestId('exact-contract-result').waitFor();
  const answer=page.waitForResponse(r=>r.url().includes('/api/agent/turn/') && r.request().method()==='GET');
  await page.getByTestId('ask-lodestar-btn').first().click();await page.getByTestId('ask-lodestar-q-0').first().click();await answer;
  const lodestar=page.getByRole('dialog',{name:'Lodestar research'});await lodestar.getByRole('article',{name:'Research answer for SPY'}).waitFor();await page.screenshot({path:path.join(evidence,'lodestar-1440.png'),fullPage:true});
  await lodestar.getByRole('button',{name:'Close',exact:true}).click();
  const handoff=page.getByRole('region',{name:'Public agent review'});await handoff.getByLabel('Execution owner').selectOption('PUBLIC_NATIVE_AGENT');await handoff.getByRole('button',{name:'Prepare dated brief'}).click();assert((await handoff.getByLabel('Editable Public brief').inputValue()).includes('Premium budget: UNSET'));await page.screenshot({path:path.join(evidence,'public-handoff-1440.png'),fullPage:true});receipt.checks.push('owning-contract deterministic draft + manual native brief, no execution');
  await page.keyboard.press('Escape');
  await navigate('trinity');for(const width of [1440,1280,390])await capture('triad',width);
  await navigate('heatseeker');await page.setViewportSize({width:1440,height:1000});await page.getByRole('grid').first().waitFor();
  const worker=context.serviceWorkers()[0] || await context.waitForEvent('serviceworker',{timeout:15000});
  const before=await page.evaluate(()=>({width:innerWidth,dpr:devicePixelRatio}));
  const tab=await worker.evaluate(async url=>(await chrome.tabs.query({})).find(t=>t.url?.startsWith(url)).id,origin);
  await worker.evaluate(async id=>chrome.tabs.setZoom(id,2),tab);await page.waitForTimeout(250);
  const factor=await worker.evaluate(async id=>chrome.tabs.getZoom(id),tab),after=await page.evaluate(()=>({width:innerWidth,dpr:devicePixelRatio,cssZoom:getComputedStyle(document.body).zoom,visualScale:visualViewport.scale}));
  assert.strictEqual(factor,2);assert(after.width<=before.width*.51);assert.strictEqual(after.cssZoom,'1');assert.strictEqual(after.visualScale,1);
  receipt.nativeZoom={method:'chrome.tabs.setZoom; no CSS/pinch emulation',factor,before,after};
  await page.getByRole('grid').first().evaluate(e=>e.scrollIntoView({block:'center'}));const cdp=await context.newCDPSession(page);const native=await cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false,fromSurface:true});fs.writeFileSync(path.join(evidence,'solstice-native200.png'),Buffer.from(native.data,'base64'));await cdp.detach();
  assert.strictEqual(receipt.pageErrors.length,0,receipt.pageErrors.join('; '));assert.strictEqual(receipt.forbiddenMutations.length,0);assert.deepStrictEqual(sourceHashes(),source);
  receipt.status='passed_fixture_full_app_browser';
 }catch(error){receipt.status='failed';receipt.failure=error.message;console.error(error.stack);process.exitCode=1;}
 finally{if(context)await context.close();await new Promise(resolve=>server.close(resolve));if(temp)fs.rmSync(temp,{recursive:true,force:true});fs.writeFileSync(path.join(evidence,'browser-receipt.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({status:receipt.status,routes:receipt.routes.length,viewports:receipt.viewports.length,pageErrors:receipt.pageErrors.length,failure:receipt.failure}));}
})();
