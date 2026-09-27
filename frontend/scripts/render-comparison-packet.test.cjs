const test = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const os = require('node:os');
const {spawnSync} = require('node:child_process');
const {renderPacket} = require('./render-comparison-packet.cjs');
const root = path.resolve(__dirname, '..');
const displayPaths = ['src/agent/AgentPanelAnswer.jsx', 'src/agent/Evidence.jsx',
  'src/agent/chartReading.js', 'src/agent/AgentModelSettings.jsx', 'src/config/api.js',
  'scripts/render-comparison-packet.cjs', 'package.json', 'package-lock.json',
  'src/agent/requestFailure.js', 'src/agent/useAgentStream.js', 'src/agent/AgentProvider.jsx', 'src/agent/AgentConversation.jsx'];
function comparisonFixture() {
  const base = fixture();
  return {mode: 'comparison', cases: Array.from({length: 32}, (_, i) => ({...structuredClone(base.cases[0]), id: `synthetic_${i}`})),
    expected_display: {files: Object.fromEntries(displayPaths.map(file => [file,
      crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex')]))}};
}
function fixture() {
  const turn = {ticker: 'SPY', horizon: 'all', status: 'completed', answer: {
    summary: 'Saved price is 123.45 USD.', mode: 'model-assisted', model_status: 'SECRET MODEL STATUS',
    usage: [{provider: 'SECRET PROVIDER', model: 'SECRET MODEL'}],
    sections: [{name: 'Market', text: 'This is the saved observation.'}],
    facts: [{id: 'dev-price', ticker: 'SPY', metric: 'Underlying price', value: 123.45,
      unit: 'USD', source: 'SYNTHETIC_DEVELOPMENT_ONLY', status: 'ok', event_time: '2026-09-28T14:29:50Z'}],
    gaps: [], snapshots: []}};
  return {mode: 'development', cases: [{id: 'development_only', question: 'Explain the saved development price.',
    answers: ['arm_a', 'arm_b', 'arm_c'].map(label => ({label, status: 'executed_not_graded', turn: structuredClone(turn)}))}]};
}

test('actual component retains evidence and explanations while removing model identity', () => {
  const input = fixture();
  input.cases[0].answers[1].turn.answer.model_explanations = [{id: 'ex', text: 'An observation is not a promised fill.', kind: 'development'}];
  const before = structuredClone(input);
  const result = renderPacket(input);
  const document = new JSDOM(result.html).window.document;
  assert.equal(document.querySelectorAll('article.lodestar-answer').length, 3);
  assert.match(document.body.textContent, /123.45 USD/);
  assert.match(document.body.textContent, /An observation is not a promised fill/);
  assert.ok(!result.html.includes('SECRET'));
  assert.deepEqual(input, before);
  assert.equal(result.receipt.first_browser_display, null);
  assert.equal(result.receipt.usefulness, 'not_graded');
  assert.ok(result.receipt.source_files['src/agent/AgentPanelAnswer.jsx']);
  assert.ok(result.receipt.source_files['src/agent/Evidence.jsx']);
});

test('untrusted answer and question text is escaped without creating scripts', () => {
  const input = fixture();
  input.cases[0].question = '<img src=x onerror="alert(1)">';
  input.cases[0].answers[0].turn.answer.summary = '<script>unsafe()</script>';
  const result = renderPacket(input);
  const document = new JSDOM(result.html).window.document;
  assert.equal(document.querySelectorAll('script,img').length, 0);
  assert.match(document.body.textContent, /<script>unsafe/);
  assert.match(document.querySelector('meta[http-equiv="Content-Security-Policy"]').content, /default-src 'none'/);
});

test('unfinished outcomes stay visible and cannot be passed off as completed answers', () => {
  const input = fixture();
  input.cases[0].answers[1] = {label: 'arm_b', status: 'started_outcome_unknown'};
  input.cases[0].answers[2] = {label: 'arm_c', status: 'not_run'};
  assert.match(renderPacket(input).html, /No completed answer: started outcome unknown/);
  input.cases[0].answers[1].turn = input.cases[0].answers[0].turn;
  assert.throws(() => renderPacket(input), /Unfinished outcome/);
});

test('comparison mode cannot silently shrink the frozen denominator or reuse an arm label', () => {
  const input = fixture();
  input.mode = 'comparison';
  assert.throws(() => renderPacket(input), /All32/);
  input.mode = 'development';
  input.cases[0].answers[2].label = 'arm_b';
  assert.throws(() => renderPacket(input), /three distinct/);
});

test('ledger-only saved evidence survives masking', () => {
  const input = fixture();
  const turn = input.cases[0].answers[0].turn;
  turn.ledger = {legacy: {...turn.answer.facts[0], value: 987.65, coverage: 'Partial saved coverage'}};
  delete turn.answer.facts;
  const text = new JSDOM(renderPacket(input).html).window.document.body.textContent;
  assert.match(text, /987.65 USD/);
  assert.match(text, /Partial saved coverage/);
});

test('comparison rejects absent or mismatched sealed display identities', () => {
  const input = comparisonFixture();
  delete input.expected_display;
  assert.throws(() => renderPacket(input), /display identit/i);
  for (const file of displayPaths) {
    const bad = comparisonFixture();
    bad.expected_display.files[file] = '0'.repeat(64);
    assert.throws(() => renderPacket(bad), /display identit/i, file);
  }
});

test('comparison requires exact source closure and rejects unsafe paths', () => {
  const input = comparisonFixture();
  delete input.expected_display.files['src/config/api.js'];
  assert.throws(() => renderPacket(input), /display identit/i);
  const extra = comparisonFixture();
  extra.expected_display.files['../package.json'] = '0'.repeat(64);
  assert.throws(() => renderPacket(extra), /display identit/i);
  const surplus = comparisonFixture();
  surplus.expected_display.files['src/agent/PaperSettings.jsx'] = crypto.createHash('sha256')
    .update(fs.readFileSync(path.join(root, 'src/agent/PaperSettings.jsx'))).digest('hex');
  assert.throws(() => renderPacket(surplus), /sealed source closure/);
});

test('comparison with matching identities renders all synthetic cases and records binding', () => {
  const input = comparisonFixture();
  const result = renderPacket(input);
  assert.equal(new JSDOM(result.html).window.document.querySelectorAll('article[data-arm]').length, 96);
  assert.deepEqual(result.receipt.display_files, input.expected_display.files);
});

test('display identity is checked again after answer preparation', () => {
  const input = comparisonFixture();
  let prepared = false;
  Object.defineProperty(input.cases[0].answers[0].turn.answer, 'summary', {
    get() { prepared = true; return 'Synthetic saved observation'; }, enumerable: true,
  });
  const original = fs.readFileSync;
  fs.readFileSync = function(file, ...args) {
    if (prepared && file === path.join(root, 'package.json')) return Buffer.from('changed after initial verification');
    return original.call(this, file, ...args);
  };
  try {
    assert.throws(() => renderPacket(input), /Changed display identity: package.json/);
    assert.equal(prepared, true);
  } finally { fs.readFileSync = original; }
});

test('failed, unknown, and unrun answers remain explicit; refusal text stays escaped', () => {
  const input = fixture();
  input.cases[0].answers = ['failed', 'started_outcome_unknown', 'not_run'].map((status, i) => ({label: `arm_${'abc'[i]}`, status}));
  let document = new JSDOM(renderPacket(input).html).window.document;
  assert.equal(document.querySelectorAll('article.lodestar-answer').length, 0);
  for (const answer of input.cases[0].answers) assert.ok(document.body.textContent.includes('No completed answer: ' + answer.status.replaceAll('_', ' ')));
  input.cases[0].answers[0] = {label: 'arm_a', status: 'executed_not_graded', refusal: {status:422,body:{detail:'<script>declined</script>'}}};
  document = new JSDOM(renderPacket(input).html).window.document;
  assert.equal(document.querySelectorAll('script').length, 0);
  assert.equal(document.querySelector('[role="alert"]').textContent, '<script>declined</script>');
  assert.ok(document.body.textContent.includes('<script>declined</script>'));
  input.cases[0].answers[0].turn = fixture().cases[0].answers[0].turn;
  assert.throws(() => renderPacket(input), /Invalid refused/);
  input.cases[0].answers[0] = {label: 'arm_a', status: 'success'};
  assert.throws(() => renderPacket(input), /Unknown outcome/);
});

test('source labels, stale time, gaps, referenced facts and coverage remain inspectable', () => {
  const input = fixture();
  const answer = input.cases[0].answers[0].turn.answer;
  answer.facts[0].status = 'stale';
  answer.facts[0].coverage = {available: 3, expected: 5};
  answer.gaps = ['No current quote'];
  answer.model_relationships = ['This saved quote may have changed.'];
  answer.model_sections = [{name: 'Saved context', text: 'Use the dated observation.', fact_ids: ['dev-price']}];
  const document = new JSDOM(renderPacket(input).html).window.document;
  const first = document.querySelector('article[data-arm="arm_a"]');
  for (const value of ['SYNTHETIC_DEVELOPMENT_ONLY', 'stale', '2026-09-28T14:29:50Z', '{"available":3,"expected":5}',
    'No current quote', 'This saved quote may have changed.', 'Use the dated observation.', 'Underlying price: 123.45 USD']) {
    assert.ok(first.textContent.includes(value), value);
  }
});

test('real offline command writes inspectable output and refuses overwrite', () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'floww-display-review-'));
  try {
    const input = path.join(temp, 'development.json');
    const output = path.join(temp, 'rendered');
    fs.writeFileSync(input, JSON.stringify(fixture()));
    const args = [path.join(__dirname, 'render-comparison-packet.cjs'), input, output];
    const result = spawnSync(process.execPath, args, {windowsHide: true, encoding: 'utf8'});
    assert.equal(result.status, 0, result.stderr);
    const html = fs.readFileSync(path.join(output, 'answers.html'), 'utf8');
    const receipt = JSON.parse(fs.readFileSync(path.join(output, 'receipt.json')));
    assert.equal(receipt.html_sha256, crypto.createHash('sha256').update(html).digest('hex'));
    assert.equal(receipt.input_file_sha256, crypto.createHash('sha256').update(fs.readFileSync(input)).digest('hex'));
    assert.equal(new JSDOM(html).window.document.querySelectorAll('article.lodestar-answer').length, 3);
    assert.equal(receipt.first_browser_display, null);
    const again = spawnSync(process.execPath, args, {windowsHide: true, encoding: 'utf8'});
    assert.notEqual(again.status, 0);
    assert.equal(fs.readFileSync(path.join(output, 'answers.html'), 'utf8'), html);
  } finally {
    // The target is exactly the fresh directory created for this test, under the OS temp root.
    assert.equal(path.dirname(temp), path.resolve(os.tmpdir()));
    assert.ok(path.basename(temp).startsWith('floww-display-review-'));
    fs.rmSync(temp, {recursive: true});
  }
});


test('refusal display shares live request rules and rejects the old free-text adapter', () => {
  const input=fixture();
  input.cases[0].answers[0]={label:'arm_a',status:'executed_not_graded',refusal:{status:422,body:{detail:'Choose at most three valid tickers'}}};
  input.cases[0].answers[1]={label:'arm_b',status:'executed_not_graded',refusal:{status:500,body:{detail:'Private server failure'}}};
  input.cases[0].answers[2]={label:'arm_c',status:'executed_not_graded',refusal:{status:422,body:{detail:['invalid shape']}}};
  const result=renderPacket(input);
  const document=new JSDOM(result.html).window.document;
  assert.deepEqual([...document.querySelectorAll('[role="alert"]')].map(el=>el.textContent),[
    'Choose at most three valid tickers','Research request could not start','Research request could not start']);
  assert.ok(result.receipt.source_files['src/agent/requestFailure.js']);
  assert.ok(!result.html.includes('Private server failure'));
  input.cases[0].answers[0].refusal='Invented display text';
  assert.throws(()=>renderPacket(input),/Invalid refused-request display/);
});
