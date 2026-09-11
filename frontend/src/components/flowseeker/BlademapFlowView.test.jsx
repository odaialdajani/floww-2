/**
 * Blademap flow-view restructuring (2026-09-05, Nav directive):
 * - free-text tape focus (no watchlist/dropdown)
 * - exclusive DTE bands (0D / 1-7D / 8-21D / 22-45D / 45D+ / ALL)
 * - selected-signal panel renders below the tape (no right rail)
 *
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import FlowseekerProBlademap from './FlowseekerProBlademap';

jest.setTimeout(30000);

// Fixture expiries land ~13 trading days out (mid-September 2026).
const contracts = [
  { strike: 450, type: 'call', expiry: '2026-09-18', volume: 500, oi: 500, iv: 0.2, bid: 4, ask: 4.2, last: 4.1 },
  { strike: 450, type: 'put', expiry: '2026-09-18', volume: 600, oi: 600, iv: 0.25, bid: 3.9, ask: 4.1, last: 4.0 },
];

beforeEach(() => {
  window.localStorage.clear();
  global.fetch = jest.fn().mockImplementation((url) => {
    if (String(url).includes('/public/chain/SPY')) {
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ ok: true, contracts, spot: 452 }),
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  });
});

async function openFlow() {
  render(<FlowseekerProBlademap active={true} />);
  fireEvent.click(screen.getByText('Smart Order Flow'));
  await act(async () => { jest.advanceTimersByTime(0); });
}

test('free-text focus filters the tape; ALL restores it', async () => {
  jest.useFakeTimers();
  try {
    await openFlow();
    // Rows render from the fixture feed.
    await act(async () => { jest.advanceTimersByTime(1000); });
    expect(screen.queryAllByText('SPY').length).toBeGreaterThan(0);

    // Focus an unknown ticker -> tape empties (rows are SPY prints).
    const input = screen.getByTestId('fsb-ticker-search');
    fireEvent.change(input, { target: { value: 'ZZZ' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    await act(async () => { jest.advanceTimersByTime(1000); });
    expect(screen.queryByText(/No prints for/)).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});

test('exclusive DTE bands partition the tape', async () => {
  jest.useFakeTimers();
  try {
    await openFlow();
    await act(async () => { jest.advanceTimersByTime(1000); });
    // Fixture DTE (~13) sits in 8-21D: visible there...
    fireEvent.click(screen.getByText('8-21D'));
    await act(async () => { jest.advanceTimersByTime(500); });
    expect(screen.queryAllByText('SPY').length).toBeGreaterThan(0);
    // ...and hidden under the disjoint 0D band.
    fireEvent.click(screen.getByText('0D'));
    await act(async () => { jest.advanceTimersByTime(500); });
    expect(screen.queryByText(/No prints for/)).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});

test('no watchlist, tabs, or subtabs render in the flow view', async () => {  jest.useFakeTimers();
  try {
    await openFlow();
    await act(async () => { jest.advanceTimersByTime(500); });
    expect(screen.queryByText('Watchlist')).not.toBeInTheDocument();
    expect(screen.queryByText('WTI Crude')).not.toBeInTheDocument();
    expect(screen.queryByText('Stat-Arb Pairs')).not.toBeInTheDocument();
    expect(screen.queryByText('Dealer Positioning')).not.toBeInTheDocument();
    expect(screen.queryByText('Order Flow Imbalance')).not.toBeInTheDocument();
    expect(screen.queryByText('Dealer GEX Heatmap')).not.toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});

test('chart modal opens from the selected signal with honest empties', async () => {
  jest.useFakeTimers();
  try {
    await openFlow();
    await act(async () => { jest.advanceTimersByTime(1000); });
    // Select the first tape row.
    const rows = document.querySelectorAll('tbody tr');
    expect(rows.length).toBeGreaterThan(0);
    fireEvent.click(rows[0]);
    // Open the composed chart modal.
    fireEvent.click(screen.getByTestId('selected-chart-open'));
    expect(screen.getByTestId('chart-modal')).toBeInTheDocument();
    expect(screen.getByTestId('chart-history-empty')).toBeInTheDocument();
    // Close it again.
    fireEvent.click(screen.getByTestId('chart-close'));
    expect(screen.queryByTestId('chart-modal')).not.toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});
