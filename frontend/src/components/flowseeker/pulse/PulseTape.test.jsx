/** @jest-environment jsdom */
import React from 'react';
import { render, screen } from '@testing-library/react';
import OverviewBar from '../pulse/OverviewBar.jsx';
import PulseTape from '../pulse/PulseTape.jsx';
import pulseRows from '../fixtures/pulseRows.json';
import overviewPayloads from '../fixtures/overviewPayloads.json';

describe('OverviewBar states', () => {
  it('renders Bullish fixture', () => {
    const p = overviewPayloads.find((x) => x.name === 'bullish');
    render(<OverviewBar rows={p.rows} />);
    expect(screen.getByTestId('overview-session').textContent).toMatch(/Bullish/);
    expect(screen.getByTestId('overview-rvol').textContent).toMatch(/needs baseline/);
  });
  it('empty shows honest-empty', () => {
    render(<OverviewBar rows={[]} />);
    expect(screen.getByTestId('overview-empty')).toBeInTheDocument();
  });
  it('loading/error/frozen', () => {
    const { rerender } = render(<OverviewBar rows={[]} state="loading" />);
    expect(screen.getByTestId('overview-loading')).toBeInTheDocument();
    rerender(<OverviewBar rows={[]} state="error" />);
    expect(screen.getByTestId('overview-error')).toBeInTheDocument();
    rerender(<OverviewBar rows={[{ type: 'call', premium: 1e5 }]} state="frozen" />);
    expect(screen.getByTestId('overview-frozen')).toBeInTheDocument();
  });
});

describe('PulseTape', () => {
  it('renders fill + side + spread bar', () => {
    render(<PulseTape rows={pulseRows} />);
    expect(screen.getAllByTestId('pulse-row').length).toBe(8);
    expect(screen.getAllByTestId('pulse-fill').length).toBe(8);
    expect(screen.getAllByTestId('pulse-side').length).toBe(8);
  });
  it('no-quote rows show NO_QUOTE or LOCKED (never guessed)', () => {
    render(<PulseTape rows={pulseRows} />);
    const sides = screen.getAllByTestId('pulse-side').map((el) => el.textContent);
    const nonOk = sides.filter((s) => s === 'NO_QUOTE' || s === 'LOCKED');
    expect(nonOk.length).toBeGreaterThanOrEqual(3);
  });
  it('honest states: loading/empty/error/frozen', () => {
    const { rerender } = render(<PulseTape rows={[]} state="loading" />);
    expect(screen.getByTestId('pulse-loading')).toBeInTheDocument();
    rerender(<PulseTape rows={[]} state="empty" />);
    expect(screen.getByTestId('pulse-empty')).toBeInTheDocument();
    rerender(<PulseTape rows={[]} state="error" />);
    expect(screen.getByTestId('pulse-error')).toBeInTheDocument();
    rerender(<PulseTape rows={pulseRows} frozen />);
    expect(screen.getByTestId('pulse-frozen')).toBeInTheDocument();
  });
});
