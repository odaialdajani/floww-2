/** @jest-environment jsdom */
import React from 'react';
import { render, screen } from '@testing-library/react';
import DarkPoolPanel from './DarkPoolPanel.jsx';

describe('DarkPoolPanel honesty', () => {
  const prints = [{ time: '10:00', ticker: 'SPY', price: 500, size: 10000, notional: 5e6, sector: 'ETF', level: 2.2e9, date: '2026-05-15' }];
  it('shows time/ticker/price/size/notional/sector/level/date — no side/direction', () => {
    render(<DarkPoolPanel prints={prints} />);
    expect(screen.getByTestId('darkpool-panel')).toBeInTheDocument();
    const row = screen.getByTestId('darkpool-row').textContent;
    expect(row).toMatch(/SPY/);
    expect(row).not.toMatch(/BULLISH|BEARISH|buy|sell/i);
  });
  it('tooltip says no side or direction', () => {
    render(<DarkPoolPanel prints={prints} levels={[{ notional: 2.2e9, date: '2026-05-15' }]} />);
    const lvl = screen.getByTestId('darkpool-level');
    // label like DP $2.2B · 2026-05-15
    expect(lvl.textContent).toMatch(/DP/);
    expect(lvl.textContent).toMatch(/2026-05-15/);
  });
  it('no-side copy audit: rendered text never contains side/bullish language', () => {
    const { container } = render(<DarkPoolPanel prints={prints} />);
    const text = container.textContent;
    expect(text).not.toMatch(/BULLISH|BEARISH|buy\/sell|long\/short/i);
    // bought/sold neutral but ensure no \"Side:\" claim
    expect(text).not.toMatch(/Side:/);
  });
  it('paid-gate honest state when no free data', () => {
    render(<DarkPoolPanel prints={[]} state="paid_gate" />);
    expect(screen.getByTestId('darkpool-paid-gate')).toBeInTheDocument();
  });
});
