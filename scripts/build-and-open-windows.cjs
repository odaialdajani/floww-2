'use strict';
// Windows desktop launcher. Builds saved local source; never pulls or places orders.
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const net = require('node:net');
const cp = require('node:child_process');
const os = require('node:os');
const { pathToFileURL } = require('node:url');
const root = path.resolve(__dirname, '..');
const frontend = path.join(root, 'frontend');
const backend = path.join(root, 'backend');
const profile = process.env.USERPROFILE || os.homedir();
const local = process.env.LOCALAPPDATA || path.join(profile, 'AppData', 'Local');
Object.assign(process.env, {SystemRoot: 'C:\\Windows', SYSTEMROOT: 'C:\\Windows', WINDIR: 'C:\\Windows', SystemDrive: 'C:', SYSTEMDRIVE: 'C:', USERPROFILE: profile, LOCALAPPDATA: local, APPDATA: process.env.APPDATA || path.join(profile,'AppData','Roaming'), ComSpec: 'C:\\Windows\\System32\\cmd.exe', PATHEXT: '.COM;.EXE;.BAT;.CMD'});
const stateDir = path.join(local, 'FLOWW', 'desktop-launcher');
fs.mkdirSync(stateDir, {recursive:true});
const lockFile = path.join(stateDir, 'building.lock');
const activeFile = path.join(stateDir, 'latest-build.json');
const node = process.execPath;
const craco = path.join(frontend,'node_modules','@craco','craco','dist','bin','craco.js');
const python = ['.venv313','.venv'].map(v=>path.join(backend,v,'Scripts','python.exe')).find(fs.existsSync);
const mongoDir = path.join(local,'FLOWW','mongodb-8.0.32');
const mongo = path.join(mongoDir,'package','mongodb-win32-x86_64-windows-8.0.32','bin','mongod.exe');
const psDirs = path.join(process.env.ProgramFiles || 'C:\\Program Files','PowerShell');
const ps = (fs.existsSync(psDirs) ? fs.readdirSync(psDirs).sort().reverse().map(d=>path.join(psDirs,d,'pwsh.exe')).find(fs.existsSync) : null) || 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe';
const delay = ms => new Promise(r=>setTimeout(r,ms));
const escape = s => String(s).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
function run(exe,args,options={}) {return new Promise((resolve,reject)=>{cp.execFile(exe,args,{cwd:root,windowsHide:true,encoding:'utf8',maxBuffer:4*1024*1024,...options},(err,stdout,stderr)=>{if(err) reject(Object.assign(err,{stdout,stderr}));else resolve(stdout);});});}
function powershell(script) {return run(ps,['-NoProfile','-NonInteractive','-EncodedCommand',Buffer.from("$ProgressPreference='SilentlyContinue'; "+script,'utf16le').toString('base64')]);}
function alive(pid) {try {process.kill(pid,0); return true;}catch{return false;}}
function spawnService(exe,args,cwd,name,env=process.env) {
  const out=fs.openSync(path.join(stateDir,name+'.out.log'),'a');
  const err=fs.openSync(path.join(stateDir,name+'.err.log'),'a');
  const child=cp.spawn(exe,args,{cwd,env,windowsHide:true,detached:true,stdio:['ignore',out,err]});
  fs.closeSync(out);fs.closeSync(err);child.unref();
  fs.appendFileSync(path.join(stateDir,'services.log'),new Date().toISOString()+' '+name+' pid='+child.pid+'\n');
  return child;
}
function portOpen(port) {return new Promise(resolve=>{const socket=net.createConnection({host:'127.0.0.1',port});let done=false;const end=v=>{if(done)return;done=true;socket.destroy();resolve(v);};socket.once('connect',()=>end(true));socket.once('error',()=>end(false));socket.setTimeout(1500,()=>end(false));});}
async function json(url) {const r=await fetch(url,{signal:AbortSignal.timeout(8000)});if(!r.ok)throw new Error('Service check failed ('+r.status+').');return r.json();}
async function waitUntil(check,label,seconds=120) {const end=Date.now()+seconds*1000;while(Date.now()<end){try{if(await check())return;}catch{}await delay(1000);}throw new Error(label+' did not start.');}
async function owner(port) {
  const rows=(await run('C:\\Windows\\System32\\netstat.exe',['-ano','-p','tcp'])).split(/\r?\n/);
  const row=rows.map(s=>s.trim().split(/\s+/)).find(a=>a[0]==='TCP'&&a[1].endsWith(':'+port)&&a[3]==='LISTENING');
  if(!row)throw new Error('Cannot identify the app already using port '+port+'.');
  return JSON.parse((await powershell('Get-CimInstance Win32_Process -Filter "ProcessId='+Number(row[4])+'" | Select-Object ProcessId,ParentProcessId,CommandLine,CreationDate | ConvertTo-Json -Compress')).trim());
}
async function newestSource(dir) {
  let newest=0;
  const excluded=new Set(['.venv','.venv313','__pycache__','tests','logs','data','.pytest_cache','.ruff_cache']);
  for(const item of await fsp.readdir(dir,{withFileTypes:true})){
    if(item.isDirectory()&&!excluded.has(item.name)&&!item.name.startsWith('.'))newest=Math.max(newest,await newestSource(path.join(dir,item.name)));
    else if(item.isFile()&&(item.name.endsWith('.py')||item.name==='.env'))newest=Math.max(newest,(await fsp.stat(path.join(dir,item.name))).mtimeMs);
  }
  return newest;
}
async function currentBackend() {
  if(!await portOpen(8001))return false;
  const who=await owner(8001);
  const command=String(who.CommandLine||'').replaceAll('\\','/').toLowerCase();
  if(!command.includes(root.replaceAll('\\','/').toLowerCase())||!command.includes('uvicorn')||!command.includes('8001'))throw new Error('A different app uses the data-service address. It was kept open.');
  await json('http://127.0.0.1:8001/api/health');
  if(await newestSource(backend)>Date.parse(who.CreationDate)+1000){
    update('Saved data-service changes need a restart. Choose Yes in the FLOWW2 window to continue.');
    let allowRestart=false;try {allowRestart=JSON.parse(await fsp.readFile(path.join(stateDir,'preferences.json'),'utf8')).restartFlowwForSavedChanges===true;}catch{}
    const answer=allowRestart?6:Number((await powershell("$dialog=New-Object -ComObject WScript.Shell; $dialog.Popup('FLOWW2 has saved changes. Restart FLOWW2 to load them? Your other apps stay open.',0,'FLOWW2 - Load saved changes',36)")).trim());
    if(answer!==6)throw new Error('Build completed. The earlier data service was kept open because its restart was declined.');
    const now=await owner(8001);
    if(now.ProcessId!==who.ProcessId||now.CreationDate!==who.CreationDate)throw new Error('The running app changed during confirmation. Nothing was stopped.');
    await powershell('Stop-Process -Id '+Number(who.ProcessId)+' -ErrorAction Stop');
    await waitUntil(async()=>!await portOpen(8001),'Data-service restart',20);
    return false;
  }
  return true;
}
const buildOnly=process.argv.includes('--build-only');
let stage='Preparing FLOWW2...',failure=null,done=false,progress;
function update(message){stage=message;fs.writeFileSync(path.join(stateDir,'status.json'),JSON.stringify({stage,done,failure,updatedAt:new Date().toISOString()}));}
function render(){return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="refresh" content="2"><title>FLOWW2 - Build and Open</title></head><body style="margin:0;background:#10151c;color:#eee;font:20px system-ui;display:grid;place-items:center;min-height:100vh"><main style="max-width:640px;padding:40px"><h1 style="color:#f3c44d">FLOWW2</h1><p>'+escape(stage)+'</p><p style="font-size:15px;color:#aeb9c8">'+(failure?'Build details are saved on this computer. Your existing work stays open.':'This window opens FLOWW2 when the build is ready.')+'</p></main></body></html>';}
function chromePath(){return [path.join(process.env.ProgramFiles||'C:\\Program Files','Google','Chrome','Application','chrome.exe'),path.join(local,'Google','Chrome','Application','chrome.exe')].find(fs.existsSync);}
function openBrowser(url){const chrome=chromePath();if(chrome){const c=cp.spawn(chrome,['--new-window',url],{windowsHide:false,detached:true,stdio:'ignore'});c.unref();}else{const vbs=path.join(stateDir,'open-url.vbs');fs.writeFileSync(vbs,'CreateObject("WScript.Shell").Run "'+url.replaceAll('"','""')+'", 1, False\r\n');const c=cp.spawn('C:\\Windows\\System32\\wscript.exe',[vbs],{windowsHide:true,detached:true,stdio:'ignore'});c.unref();}}
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.ico':'image/x-icon','.woff2':'font/woff2','.woff':'font/woff','.map':'application/json'};
async function serve(port=3000, directoryOverride=null) {
  const server=http.createServer(async(req,res)=>{try{
    if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
    const active=directoryOverride?{directory:directoryOverride,previous:[]}:JSON.parse(await fsp.readFile(activeFile,'utf8'));
    const name=decodeURIComponent(new URL(req.url,'http://127.0.0.1').pathname).replace(/^\/+/, '');
    if(name.includes('..')||name.includes('\\')||name.includes(':')){res.writeHead(400);res.end();return;}
    let file=path.join(active.directory,name||'index.html');
    if(!fs.existsSync(file)&&name.startsWith('static/'))for(const old of active.previous||[]){const candidate=path.join(old,name);if(fs.existsSync(candidate)){file=candidate;break;}}
    if(!fs.existsSync(file)||fs.statSync(file).isDirectory()){
      if(path.extname(name)){res.writeHead(404);res.end('Not found');return;}
      file=path.join(active.directory,'index.html');
    }
    res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':name.startsWith('static/')?'public, max-age=31536000, immutable':'no-store','X-Content-Type-Options':'nosniff'});
    if(req.method==='HEAD')res.end();else fs.createReadStream(file).pipe(res);
  }catch{res.writeHead(503);res.end('FLOWW2 build is not ready.');}});
  server.on('error',e=>{console.error(e.message);process.exitCode=1;});server.listen(port,'127.0.0.1');
}
async function launch() {
  if(fs.existsSync(lockFile)){
    try {const lock=JSON.parse(fs.readFileSync(lockFile,'utf8'));if(alive(lock.pid)){if(lock.url&&!buildOnly)openBrowser(lock.url);return;}}catch{}
    fs.unlinkSync(lockFile); // only this launcher's stale lock, never user data
  }
  const lock=fs.openSync(lockFile,'wx');fs.writeSync(lock,JSON.stringify({pid:process.pid}));fs.closeSync(lock);
  try {
    progress=http.createServer((req,res)=>{if(done&&!failure){res.writeHead(302,{Location:'http://127.0.0.1:3000/?page=flowseeker-pro&build='+Date.now(),'Cache-Control':'no-store'});res.end();}else{res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});res.end(render());}});
    await new Promise((resolve,reject)=>{progress.once('error',reject);progress.listen(0,'127.0.0.1',resolve);});
    const url='http://127.0.0.1:'+progress.address().port;
    fs.writeFileSync(lockFile,JSON.stringify({pid:process.pid,url}));if(!buildOnly)openBrowser(url);update('Building your latest saved version...');
    if(!python||!fs.existsSync(craco))throw new Error('FLOWW2 needs its existing Python and Node dependencies restored.');
    const build=path.join(stateDir,'builds',new Date().toISOString().replace(/[:.]/g,'-')+'-'+process.pid);
    const buildLog=path.join(stateDir,'build.log');const fd=fs.openSync(buildLog,'w');
    await new Promise((resolve,reject)=>{
      const child=cp.spawn(node,['--max-old-space-size=8192',craco,'build'],{cwd:frontend,env:{...process.env,CI:'false',BUILD_PATH:build,REACT_APP_BACKEND_URL:'http://127.0.0.1:8001'},windowsHide:true,stdio:['ignore',fd,fd]});
      child.once('error',reject);child.once('exit',code=>code===0?resolve():reject(new Error('The latest build failed. Build details are in build.log.')));
    }).finally(()=>fs.closeSync(fd));
    if(!fs.existsSync(path.join(build,'index.html'))||!fs.existsSync(path.join(build,'asset-manifest.json')))throw new Error('The build did not produce a complete screen.');
    if(buildOnly){
      let previous=[];try {const old=JSON.parse(await fsp.readFile(activeFile,'utf8'));previous=[old.directory,...old.previous||[]];}catch{}
      const pending=activeFile+'.pending';await fsp.writeFile(pending,JSON.stringify({directory:build,previous,builtAt:new Date().toISOString()}));await fsp.rename(pending,activeFile);
      done=true;update('Screen changes built. Existing services kept running.');return;
    }
    update('Starting the local data store...');
    if(!await portOpen(27017)){
      if(!fs.existsSync(mongo))throw new Error('The saved local data-store app could not be found.');
      spawnService(mongo,['--dbpath',path.join(mongoDir,'data'),'--bind_ip','127.0.0.1','--port','27017','--logpath',path.join(stateDir,'mongodb.log'),'--logappend'],mongoDir,'mongodb');
      await waitUntil(()=>portOpen(27017),'Local data store',45);
    }
    update('Checking the data connection...');
    if(!await currentBackend()){
      spawnService(python,['-u','-m','uvicorn','server:app','--host','127.0.0.1','--port','8001'],backend,'backend');
      await waitUntil(async()=>(await json('http://127.0.0.1:8001/api/health')).status==='healthy','Data service');
    }
    let previous=[];try {const old=JSON.parse(await fsp.readFile(activeFile,'utf8'));previous=[old.directory,...old.previous||[]];}catch{}
    const pending=activeFile+'.pending';await fsp.writeFile(pending,JSON.stringify({directory:build,previous,builtAt:new Date().toISOString()}));await fsp.rename(pending,activeFile);
    update('Opening FLOWW2...');
    if(await portOpen(3000)){
      const who=await owner(3000);const cmd=String(who.CommandLine||'').replaceAll('\\','/').toLowerCase();
      if(!cmd.includes(root.replaceAll('\\','/').toLowerCase())||(!cmd.includes('craco')&&!cmd.includes('react-scripts')&&!cmd.includes('build-and-open-windows.cjs')))throw new Error('Another app uses the FLOWW2 screen address. It was kept open.');
      const html=await fetch('http://127.0.0.1:3000/',{signal:AbortSignal.timeout(15000)}).then(r=>r.text());
      if(!html.includes('id="root"'))throw new Error('The open screen is not FLOWW2. It was kept open.');
      // The existing development server already recompiles saved screen changes.
      // A launcher-owned built server reads the latest completed build atomically.
    }else{
      spawnService(node,[__filename,'--serve'],root,'frontend');
      await waitUntil(()=>portOpen(3000),'FLOWW2 screen',30);
    }
    const quote=await json('http://127.0.0.1:8001/api/public/quotes/SPY');
    if(!quote.ok)throw new Error('FLOWW2 opened, but the market-data connection did not pass its check.');
    done=true;update('Build complete. FLOWW2 is opening.');
    fs.writeFileSync(path.join(stateDir,'last-success.json'),JSON.stringify({builtAt:new Date().toISOString(),buildDirectory:build,appUrl:'http://127.0.0.1:3000/',quoteSource:quote.data_source,quoteObservedAt:quote.spot_event_time,quoteReceivedAt:quote.spot_fetched_at}));
    await delay(15000);
  }catch(error){failure=error.message;update(failure);fs.writeFileSync(path.join(stateDir,'last-error.log'),new Date().toISOString()+' '+failure+'\n');console.error(failure);process.exitCode=1;if(!buildOnly)await delay(60000);}
  finally{if(progress)progress.close();try{fs.unlinkSync(lockFile);}catch{}}
}
if(process.argv.includes('--serve')){const option=process.argv.find(a=>a.startsWith('--port='));const port=option?Number(option.slice(7)):3000;if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('Invalid local screen port.');const built=process.argv.find(a=>a.startsWith('--build='));serve(port,built?path.resolve(built.slice(8)):null);}else launch().catch(e=>{console.error(e.message);process.exitCode=1;});
