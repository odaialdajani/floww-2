/* Offline blind-review rendering through the actual saved-answer component.
 * This produces inspectable HTML, not browser-paint or usefulness acceptance.
 * No model, provider, app-server, fetch or evaluation runner is invoked.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const babel = require('@babel/core');
const ROOT = path.resolve(__dirname, '..');
const SOURCE = path.join(ROOT, 'src') + path.sep;
const loadedSources = new Map();
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const rendererIdentity = hash(fs.readFileSync(__filename));
// These files govern the visible refusal message, but are not compiled by the answer-only renderer.
const fixedDisplayFiles = ['scripts/render-comparison-packet.cjs', 'package.json', 'package-lock.json',
  'src/agent/useAgentStream.js', 'src/agent/AgentProvider.jsx', 'src/agent/AgentConversation.jsx'];
const relative = filename => path.relative(ROOT, filename).replaceAll(path.sep, '/');

function checkDisplayFiles(files) {
  if (!files || typeof files !== 'object' || Array.isArray(files)) throw Error('Expected display identities required');
  for (const required of fixedDisplayFiles) {
    if (!Object.hasOwn(files, required)) throw Error('Missing display identity: ' + required);
  }
  for (const [file, digest] of Object.entries(files)) {
    if (!(fixedDisplayFiles.includes(file) || /^src\/(?:[\w.-]+\/)*[\w.-]+\.(?:js|jsx)$/.test(file))
        || file.split('/').some(part => part === '.' || part === '..') || !/^[a-f0-9]{64}$/.test(digest)) {
      throw Error('Invalid display identity: ' + file);
    }
    let actual;
    try { actual = hash(fs.readFileSync(path.join(ROOT, file))); }
    catch { throw Error('Unavailable display identity: ' + file); }
    if (actual !== digest || file === fixedDisplayFiles[0] && digest !== rendererIdentity) {
      throw Error('Changed display identity: ' + file);
    }
  }
}

function displayFiles() {
  return {...Object.fromEntries([...loadedSources].map(([file, digest]) => [relative(file), digest])),
    ...Object.fromEntries(fixedDisplayFiles.map(file => [file,
      file === fixedDisplayFiles[0] ? rendererIdentity : hash(fs.readFileSync(path.join(ROOT, file)))]))};
}

function checkExactDisplay(expected, actual) {
  if (Object.keys(expected).length !== Object.keys(actual).length ||
      Object.entries(actual).some(([file, digest]) => expected[file] !== digest)) {
    throw Error('Compiled display identities do not match the sealed source closure');
  }
}

function loadAnswerComponent() {
  // Rebuild the actual closure on every call, including when another caller primed require.cache.
  loadedSources.clear();
  for (const filename of Object.keys(require.cache)) {
    if (filename.startsWith(SOURCE)) delete require.cache[filename];
  }
  const originalJs = require.extensions['.js'];
  const originalJsx = require.extensions['.jsx'];
  function compile(module, filename) {
    if (!filename.startsWith(SOURCE)) return originalJs(module, filename);
    const raw = fs.readFileSync(filename);
    const identity = hash(raw);
    const transformed = babel.transformSync(raw.toString('utf8'), {
      filename, babelrc: false, configFile: false,
      presets: [[require.resolve('@babel/preset-env'), {targets: {node: 'current'}}],
                [require.resolve('@babel/preset-react'), {runtime: 'automatic'}]],
    });
    loadedSources.set(filename, identity);
    module._compile(transformed.code, filename);
  }
  try {
    require.extensions['.js'] = compile;
    require.extensions['.jsx'] = compile;
    return {Answer: require('../src/agent/AgentPanelAnswer.jsx').default,
      requestFailureText: require('../src/agent/requestFailure.js').requestFailureText};
  } finally {
    require.extensions['.js'] = originalJs;
    if (originalJsx) require.extensions['.jsx'] = originalJsx;
    else delete require.extensions['.jsx'];
  }
}

function maskedTurn(turn) {
  if (!turn || typeof turn !== 'object' || Array.isArray(turn)) throw Error('Saved turn required');
  const copy = {};
  for (const key of ['ticker', 'horizon', 'status', 'saved', 'text']) {
    if (turn[key] !== undefined) copy[key] = turn[key];
  }
  if (turn.ledger !== undefined) copy.ledger = structuredClone(turn.ledger);
  if (turn.answer) {
    copy.answer = {};
    for (const key of ['summary', 'facts', 'gaps', 'sections', 'model_explanations',
                       'model_relationships', 'model_sections', 'snapshots']) {
      if (turn.answer[key] !== undefined) copy.answer[key] = structuredClone(turn.answer[key]);
    }
  }
  return copy;
}

function renderPacket(packet) {
  if (!packet || !['comparison', 'development'].includes(packet.mode) || !Array.isArray(packet.cases)) {
    throw Error('Explicit comparison or development packet required');
  }
  if (packet.mode === 'comparison' && packet.cases.length !== 32) throw Error('All32 comparison cases required');
  const expected = packet.expected_display?.files;
  if (packet.mode === 'comparison' || packet.expected_display !== undefined) checkDisplayFiles(expected);
  const caseIds = packet.cases.map(c => c.id);
  if (new Set(caseIds).size !== caseIds.length) throw Error('Duplicate case identity');
  const {Answer, requestFailureText} = loadAnswerComponent();
  const identities = displayFiles();
  checkDisplayFiles(identities);
  if (expected) checkExactDisplay(expected, identities);
  const h = React.createElement;
  const sections = packet.cases.map(c => {
    if (typeof c.id !== 'string' || typeof c.question !== 'string' || !Array.isArray(c.answers)
        || c.answers.length !== 3 || c.answers.map(a => a.label).sort().join(',') !== 'arm_a,arm_b,arm_c') {
      throw Error('Each case requires the three distinct frozen masked arms');
    }
    return h('section', {key: c.id, 'data-case': c.id},
      h('h2', null, c.question),
      ...c.answers.map(a => {
        if (!['executed_not_graded', 'failed', 'started_outcome_unknown', 'not_run'].includes(a.status)) {
          throw Error('Unknown outcome status');
        }
        let content;
        if (a.status !== 'executed_not_graded') {
          if (a.turn || a.refusal) throw Error('Unfinished outcome cannot contain a successful answer');
          content = h('p', {role: 'status'}, 'No completed answer: ' + a.status.replaceAll('_', ' '));
        } else if (a.refusal) {
          if (a.turn || typeof a.refusal !== 'object' || Array.isArray(a.refusal)
              || !Number.isInteger(a.refusal.status) || a.refusal.status < 400 || a.refusal.status > 599
              || !Object.hasOwn(a.refusal, 'body')) throw Error('Invalid refused-request display');
          content = h('p', {role: 'alert'}, requestFailureText(a.refusal.status, a.refusal.body));
        } else {
          if (a.turn?.status !== 'completed') throw Error('Executed answer must be a completed saved turn');
          content = h(Answer, {turn: maskedTurn(a.turn)});
        }
        return h('article', {key: a.label, 'data-arm': a.label}, h('h3', null, a.label), content);
      }));
  });
  const body = renderToStaticMarkup(h('main', null,
    h('h1', null, packet.mode === 'development' ? 'Development-only display check' : 'Masked saved-answer review'),
    h('p', null, 'Provider and model-status metadata labels are hidden for review. Answer and evidence text is preserved and may name sources. Expand sections to inspect the same saved evidence. Rendering alone is not a usefulness grade or a browser timing measurement.'),
    ...sections));
  for (const [filename, identity] of loadedSources) {
    if (hash(fs.readFileSync(filename)) !== identity) throw Error('Displayed source changed during rendering');
  }
  checkDisplayFiles(identities);
  if (expected) checkExactDisplay(expected, identities);
  const html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
    + '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;">'
    + '<title>Masked saved answers</title><style>body{font:16px/1.5 system-ui;background:#11151b;color:#e6e9ef;margin:24px}main{max-width:1200px;margin:auto}section{margin:32px 0}article{padding:16px;border:1px solid #39414d;margin:12px 0}details{margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}h2{font-size:20px}small{color:#aeb9c7}</style></head><body>'
    + body + '</body></html>';
  return {html, receipt: {mode: packet.mode, cases: packet.cases.length,
    source_files: Object.fromEntries([...loadedSources].map(([p, digest]) => [relative(p), digest])),
    display_files: identities,
    react_version: React.version, node_version: process.version, html_sha256: hash(Buffer.from(html)),
    renderer_sha256: rendererIdentity, input_sha256: hash(Buffer.from(JSON.stringify(packet))),
    first_browser_display: null, usefulness: 'not_graded',
    surface: 'Actual saved-answer React component rendered offline; provider/status metadata masked; review styling only'}};
}

module.exports = {renderPacket, maskedTurn};
if (require.main === module) {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) throw Error('Expected an input packet and a new output directory');
  const raw = fs.readFileSync(input);
  const result = renderPacket(JSON.parse(raw));
  result.receipt.input_file_sha256 = hash(raw);
  fs.mkdirSync(output, {recursive: false});
  fs.writeFileSync(path.join(output, 'answers.html'), result.html, {flag: 'wx'});
  fs.writeFileSync(path.join(output, 'receipt.json'), JSON.stringify(result.receipt, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({cases: result.receipt.cases, mode: result.receipt.mode, first_browser_display: null}));
}
