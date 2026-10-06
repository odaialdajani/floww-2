/* Content binding, not a claim that an older receipt accepted newer code. */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const {execFileSync} = require('child_process');
const root = path.resolve(__dirname, '..');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function sourceHashes() {
  const files = execFileSync('git', ['--no-pager','ls-files','frontend/src','frontend/package.json','frontend/package-lock.json','frontend/craco.config.js','backend/domain','backend/server.py','backend/routes/market_data.py','backend/services/solstice_scope.py','backend/services/solstice_replay.py','backend/services/agent','backend/services/solstice_metric_contract.py','backend/services/gex_aggregator.py','backend/services/heatmap_history.py','backend/services/heatmap_snapshot.py','backend/services/solstice_enrichment.py','scripts/r11_fixture.py','scripts/r13_fixture.py','scripts/r13_browser_receipt.cjs','scripts/r13_source_binding.cjs','scripts/r14_fixture.py','scripts/r14_answer.py','scripts/r14_browser_receipt.cjs','scripts/r14_source_binding.cjs','backend/services/solstice_window.py','backend/services/gex_core.py'], {cwd:root,encoding:'utf8'}).trim().split('\n');
  return Object.fromEntries(files.map(file => [file, hash(fs.readFileSync(path.join(root,file)))]));
}
function bundleHashes() {
  const build = path.join(root,'frontend/build');
  const manifest = JSON.parse(fs.readFileSync(path.join(build,'asset-manifest.json')));
  return Object.fromEntries(Object.entries(manifest.files).filter(([k])=>/\.(js|css)$/.test(k)).map(([k,v])=>[k,hash(fs.readFileSync(path.join(build,v.replace(/^\//,''))))]));
}
module.exports = {sourceHashes,bundleHashes,hash};
if (require.main === module) {
  const before = sourceHashes();
  execFileSync('npm',['run','build'],{cwd:path.join(root,'frontend'),stdio:'inherit',env:{...process.env,CI:'true'}});
  const after = sourceHashes();
  if (JSON.stringify(before)!==JSON.stringify(after)) throw new Error('Source changed during build');
  const receipt = {sourceCommit:execFileSync('git',['--no-pager','rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),sourceHashes:after,bundleHashes:bundleHashes()};
  fs.writeFileSync(path.join(root,'frontend/build/solstice-build-receipt.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log('Build source/bundle binding written; source unchanged during compilation.');
}
