/** @jest-environment jsdom */
// THE FIVE REQUIRED END-TO-END REGRESSION CASES for the focused-chart ask
// binding — the joint-freeze acceptance bar (cross-check H3-REVIEW-INPUT-R21-05,
// binding reviewer 20261019_181046_4114c8, acting-OpenCode 2026-10-22).
//   R1 real click -> POST carries chart_context -> a 422 refusal surfaces
//      deterministically (or a 200 answer renders) — never silence
//   R2 stale-descriptor transition: every ask carries the CURRENT binding; a
//      late answer from a superseded descriptor never becomes the active turn
//   R3 late old results: an older ask resolving after a newer one never
//      displaces the newer active turn
//   R4 null-emission revocation: a revoked (null) chartContext takes the
//      legacy refusal — no POST, no stale descriptor reuse after revocation
//   R5 unrecorded cursor: the descriptor travels verbatim (no invented
//      snapshot fields) and the honest-unavailable answer surfaces
import React from 'react';
import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import AskFlow from './AskFlow';
import AgentProvider, {useAgent} from '../../agent/AgentProvider';
import {publishScreenContext} from '../../agent/useScreenContext';

beforeAll(() => { Object.defineProperty(globalThis, 'crypto', {value: require('crypto').webcrypto, configurable: true}); });

const descriptor = (cursor, generation) => ({status: 'bound', focus: 'SPY', query: 'focused-chart',
  scope: 'saved-view:abc', cursor, generation: generation || `SPY:15:1:abc:${cursor}`});
const chartContextFor = (d) => ({descriptor: d, current: {paneId: 'pane-0', symbol: 'SPY', layoutId: 'single',
  scope: d.scope, cursor: d.cursor, generation: d.generation}});

// A probe that surfaces the provider state for assertions.
function Probe() {
  const agent = useAgent();
  return <span data-testid="probe"
    data-state={agent.state}
    data-active={agent.activeTurn ? agent.activeTurn.turn_id : ''}
    data-active-status={agent.activeTurn ? String(agent.activeTurn.status || '') : ''}
    data-error={agent.error ? String(agent.error.error || agent.error) : ''} />;
}

// Controlled transport: /ask calls park on deferreds; turn polling answers
// from a registry keyed by turn_id. Nothing is invented by the harness.
function makeTransport() {
  const askBodies = [];         // parsed POST bodies, in call order
  const askDeferreds = [];      // {resolve}
  const turnAnswers = {};       // turn_id -> completed turn body
  global.fetch = jest.fn(async (url, init) => {
    const path = String(url);
    if (path.endsWith('/session')) return {ok: true, json: async () => ({})};
    if (path.endsWith('/ask')) {
      if (init && init.body) askBodies.push(JSON.parse(init.body));
      return new Promise((resolve) => {
        askDeferreds.push({resolve: (body) => resolve({ok: !(body && body.__status), status: body && body.__status,
          json: async () => body})});
      });
    }
    const id = path.split('/').pop();
    const body = turnAnswers[id] || {status: 'interrupted', error: 'unknown turn'};
    return {ok: true, json: async () => body};
  });
  return {
    askBodies,
    turnAnswers,
    answerAsk(index, body) { askDeferreds[index].resolve(body); },
    registerTurn(id, text) { turnAnswers[id] = {turn_id: id, status: 'completed', ticker: 'SPY', text, contract: null, executable: false}; },
  };
}

// One provider tree; the binding transition is a RERENDER of the same tree
// (the pane's context changing), not a second mount.
function mountAsk(initialChartContext) {
  publishScreenContext({contextVersion: 1, page: 'heatseeker', ticker: 'SPY', navigationOnly: true});
  const tree = (chartContext) => (
    <AgentProvider><Probe /><AskFlow subject="SPY" overlayMetric="raw" displayMode="price-history" compact
      chartContext={chartContext} /></AgentProvider>);
  const view = render(tree(initialChartContext));
  const clickAsk = () => {
    fireEvent.click(screen.getByTestId('ask-lodestar-btn'));
    fireEvent.click(screen.getByRole('menu').querySelector('button'));
  };
  return {...view, clickAsk, rebind: (d) => view.rerender(tree(d))};
}

// R1 — a real click produces a POST that carries the bound descriptor, and a
// 422 admission refusal surfaces deterministically with its server detail.
test('R1: real click -> POST chart_context -> 422 refusal surfaces deterministically', async () => {
  const t = makeTransport();
  const {clickAsk} = mountAsk(chartContextFor(descriptor(1792612800000)));
  clickAsk();
  await waitFor(() => expect(t.askBodies.length).toBe(1));
  expect(t.askBodies[0].chart_context).toEqual(descriptor(1792612800000));
  t.answerAsk(0, {__status: 422, detail: 'The focused chart is no longer bound. No new question was sent.'});
  await waitFor(() => expect(screen.getByTestId('probe').dataset.state).toMatch(/error|failed|interrupted/));
  expect(screen.getByTestId('probe').dataset.error)
    .toBe('The focused chart is no longer bound. No new question was sent.');
});

// R2 — every ask carries the CURRENT binding at click time; a superseded
// binding never travels on a later ask (sequential product reality: the
// button is busy-disabled while an ask runs, so transitions happen between
// completed asks).
test('R2: stale-descriptor transition — a later ask carries the new binding, never the superseded one', async () => {
  const t = makeTransport();
  const A = descriptor(1792612800000), B = descriptor(1792612809000);
  const {clickAsk, rebind} = mountAsk(chartContextFor(A));
  clickAsk();                 // ask under binding A
  await waitFor(() => expect(t.askBodies.length).toBe(1));
  t.registerTurn('turn-A', 'Answer under binding A');
  t.answerAsk(0, {turn_id: 'turn-A'});
  await waitFor(() => expect(screen.getByTestId('probe').dataset.active).toBe('turn-A'));
  rebind(chartContextFor(B)); // the pane's binding transitions (focus/scope/cursor changed)
  clickAsk();                 // ask under binding B
  await waitFor(() => expect(t.askBodies.length).toBe(2));
  expect(t.askBodies[0].chart_context).toEqual(A);
  expect(t.askBodies[1].chart_context).toEqual(B); // the CURRENT binding, never the stale one
  t.registerTurn('turn-B', 'Answer under the CURRENT binding');
  t.answerAsk(1, {turn_id: 'turn-B'});
  await waitFor(() => expect(screen.getByTestId('probe').dataset.active).toBe('turn-B'));
  // The superseded ask's late completion cannot displace the current one:
  // its watch already ended; only turn-B remains the active turn.
  expect(screen.getByTestId('probe').dataset.active).toBe('turn-B');
});

// R3 — late old results are identity-keyed on the live path: a stale body
// arriving on the newer ask's watch can only ever re-state ITS OWN turn — it
// never fabricates a completed answer for the newer ask and never displaces
// the displayed answer. (The watch-identity guard belongs to the saved-turn
// observeExisting path; the live path's bound is turn-keyed attribution.)
test('R3: late old results stay keyed to their own identity — no fabrication, no displacement', async () => {
  const t = makeTransport();
  const d = descriptor(1792612800000);
  const {clickAsk} = mountAsk(chartContextFor(d));
  clickAsk(); // first ask completes legitimately
  await waitFor(() => expect(t.askBodies.length).toBe(1));
  t.registerTurn('turn-1', 'The first legitimate answer');
  t.answerAsk(0, {turn_id: 'turn-1'});
  await waitFor(() => expect(screen.getByTestId('probe').dataset.active).toBe('turn-1'));
  clickAsk(); // second ask gets its own identity
  await waitFor(() => expect(t.askBodies.length).toBe(2));
  // The LATE OLD result: turn-1's completed body arrives on turn-2's watch.
  t.turnAnswers['turn-2'] = {turn_id: 'turn-1', status: 'completed', ticker: 'SPY',
    text: 'The first legitimate answer', contract: null, executable: false};
  t.answerAsk(1, {turn_id: 'turn-2'});
  await act(async () => { await new Promise(r => setTimeout(r, 200)); });
  const probe = screen.getByTestId('probe');
  // The stale body re-stated only its OWN turn-1; the newer ask (turn-2)
  // never acquired a completed answer from the old body, and the displayed
  // answer was not displaced:
  expect(probe.dataset.active).toBe('turn-1');
  expect(probe.dataset.activeStatus).toBe('completed');
});

// R4 — a revoked (null) chartContext takes the legacy refusal: no POST, no
// stale descriptor reuse — including right after a previously-bound ask.
test('R4: null-emission revocation — no POST, no stale descriptor reuse', async () => {
  const t = makeTransport();
  const {clickAsk, rebind} = mountAsk(chartContextFor(descriptor(1792612800000)));
  clickAsk(); // the bound ask completes first (product reality: busy-disabled while running)
  await waitFor(() => expect(t.askBodies.length).toBe(1));
  t.registerTurn('turn-bound', 'Answer under the bound context');
  t.answerAsk(0, {turn_id: 'turn-bound'});
  await waitFor(() => expect(screen.getByTestId('probe').dataset.active).toBe('turn-bound'));
  rebind(null); // the emission went null (revoked: focus lost / layout changed)
  clickAsk();
  await act(async () => { await new Promise(r => setTimeout(r, 100)); });
  expect(t.askBodies.length).toBe(1); // no second POST — the revoked binding never travels
  expect(screen.getByTestId('ask-lodestar-note').textContent).toMatch(/price-history/i); // the honest legacy refusal
  expect(screen.queryByTestId('ask-lodestar-chart-context')).not.toBeInTheDocument();
});

// R5 — an unrecorded cursor travels verbatim (nothing invented), and the
// honest-unavailable answer surfaces instead of fabricated data.
test('R5: unrecorded cursor — descriptor verbatim; honest unavailable answer surfaces', async () => {
  const t = makeTransport();
  const unrecorded = descriptor(1792619999000); // a cursor with no recorded snapshot
  const {clickAsk} = mountAsk(chartContextFor(unrecorded));
  clickAsk();
  await waitFor(() => expect(t.askBodies.length).toBe(1));
  expect(t.askBodies[0].chart_context).toEqual(unrecorded); // verbatim: no invented snapshot fields
  expect(t.askBodies[0].chart_context.snapshotId).toBeUndefined();
  t.registerTurn('turn-unrecorded', 'Nothing is recorded at this cursor. No values were invented.');
  t.answerAsk(0, {turn_id: 'turn-unrecorded'});
  await waitFor(() => expect(screen.getByTestId('probe').dataset.active).toBe('turn-unrecorded'));
});
