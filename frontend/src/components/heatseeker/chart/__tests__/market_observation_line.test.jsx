/** @jest-environment jsdom */
// The MAIN Market context header's observation line — RED-first.
// New pure Market-local component MarketObservationLine.jsx (root 09:20
// legibility defect): the raw snapshot UUID / full UTC clock / source string
// move behind a NAMED CLOSED Provenance detail; the visible line carries
// only LIVE/REPLAY, quality, and the honest observation age. Every exact
// field stays reachable; freshness is NEVER invented.
import React from 'react';
import { act, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import MarketObservationLine from '../../../triad/MarketObservationLine';

const NOW = Date.parse('2026-10-26T14:00:00Z');

test('the visible line is readable: LIVE/REPLAY + quality + the honest age — no raw UUID/UTC/source prose', () => {
  render(<MarketObservationLine
    replay={false}
    data={{ snapshotId: 'snap-7a1e9d2f-uuid', asof: '2026-10-26T11:55:00Z',
      data_source: 'public_equities_chain_v3', formula_version: 'gex.v2' }}
    quality={{ state: 'verified' }}
    now={() => NOW} />);
  const line = screen.getByTestId('triad-observation-line');
  expect(line).toHaveTextContent(/LIVE/);
  expect(line).toHaveTextContent(/quality verified/);
  expect(line).toHaveTextContent(/2h 5m ago/);            // honest age from the actual asof
  // the raw identifiers are NOT in the readable line
  expect(line.textContent).not.toMatch(/snap-7a1e9d2f-uuid/);
  expect(line.textContent).not.toMatch(/2026-10-26T11:55:00Z/);
  expect(line.textContent).not.toMatch(/public_equities_chain_v3/);
});

test('the named CLOSED Provenance detail carries every exact field', () => {
  render(<MarketObservationLine
    replay={false}
    data={{ snapshotId: 'snap-7a1e9d2f-uuid', asof: '2026-10-26T11:55:00Z',
      data_source: 'public_equities_chain_v3', formula_version: 'gex.v2',
      event_time: '2026-10-26T11:54:12Z' }}
    quality={{ state: 'verified' }}
    now={() => NOW} />);
  const details = screen.getByTestId('triad-provenance-details');
  expect(details).toHaveTextContent(/Provenance/);        // the NAMED summary
  expect(details.open).toBe(false);                        // CLOSED by default
  const body = details.textContent;
  expect(body).toMatch(/snap-7a1e9d2f-uuid/);              // exact snapshot id reachable
  expect(body).toMatch(/2026-10-26T11:55:00Z/);            // the full UTC clock reachable
  expect(body).toMatch(/public_equities_chain_v3/);        // the source string reachable
  expect(body).toMatch(/gex\.v2/);                          // the formula reachable
  expect(body).toMatch(/2026-10-26T11:54:12Z/);            // the market observation clock reachable
});

test('absent asof -> NO age is shown — freshness is never invented', () => {
  render(<MarketObservationLine replay={false}
    data={{ snapshotId: 'snap-x', data_source: 'src' }} quality={{ state: 'unknown' }} now={() => NOW} />);
  const line = screen.getByTestId('triad-observation-line');
  expect(line.textContent).not.toMatch(/ago/);             // no fabricated age
  expect(line).toHaveTextContent(/LIVE/);                  // the identity still shows
  expect(screen.getByTestId('triad-provenance-details')).toHaveTextContent(/time unknown/);
});

test('no snapshot: the honest no-snapshot state is preserved', () => {
  render(<MarketObservationLine replay={false} data={null} quality={null} now={() => NOW} />);
  expect(screen.getByTestId('triad-observation-line')).toHaveTextContent(/no snapshot/);
  expect(screen.getByTestId('triad-observation-line')).toHaveTextContent(/quality unknown/);
});

test('age formatting is honest at the boundaries; replay keeps its identity', () => {
  const { rerender } = render(<MarketObservationLine replay
    data={{ asof: '2026-10-26T13:59:40Z' }} quality={{ state: 'verified' }} now={() => NOW} />);
  expect(screen.getByTestId('triad-observation-line')).toHaveTextContent(/REPLAY/);
  expect(screen.getByTestId('triad-observation-line')).toHaveTextContent(/20s ago/);
  rerender(<MarketObservationLine replay data={{ asof: '2026-10-26T13:30:00Z' }} quality={{ state: 'verified' }} now={() => NOW} />);
  expect(screen.getByTestId('triad-observation-line')).toHaveTextContent(/30m ago/);
  rerender(<MarketObservationLine replay={false} data={{ asof: '2026-10-24T14:00:00Z' }} quality={{ state: 'verified' }} now={() => NOW} />);
  expect(screen.getByTestId('triad-observation-line')).toHaveTextContent(/2d ago/);
});

test('an unparseable asof renders no age either — the same honesty rule', () => {
  render(<MarketObservationLine replay={false} data={{ asof: 'not-a-clock' }} quality={{ state: 'verified' }} now={() => NOW} />);
  expect(screen.getByTestId('triad-observation-line').textContent).not.toMatch(/ago/);
});

test('an idle displayed reading ages without a parent render or a provider request', () => {
  jest.useFakeTimers('modern');
  jest.setSystemTime(NOW);
  const view = render(<MarketObservationLine replay={false}
    data={{ snapshotId: 'snap-idle', asof: '2026-10-26T13:59:40Z' }} quality={{ state: 'usable' }} />);
  try {
    expect(screen.getByTestId('triad-observation-line')).toHaveTextContent('20s ago');
    act(() => { jest.advanceTimersByTime(45000); });
    expect(screen.getByTestId('triad-observation-line')).toHaveTextContent('1m ago');
    expect(screen.getByTestId('triad-observation-line')).toHaveTextContent('snapshot age');
    expect(screen.getByTestId('triad-observation-line').textContent).not.toMatch(/observed/);
    view.unmount();
    expect(jest.getTimerCount()).toBe(0);
  } finally {
    view.unmount();
    jest.useRealTimers();
  }
});

test('a future generation clock is disclosed rather than presented as a fresh zero-second observation', () => {
  render(<MarketObservationLine replay={false}
    data={{ snapshotId: 'snap-future', asof: '2026-10-26T14:01:00Z' }} quality={{ state: 'usable' }} now={() => NOW} />);
  expect(screen.getByTestId('triad-observation-line')).toHaveTextContent('snapshot clock ahead');
  expect(screen.getByTestId('triad-observation-line').textContent).not.toMatch(/0s ago/);
});
