/** @jest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ChartModal from './ChartModal.jsx';

describe('ChartModal', () => {
  const row = { ticker: 'SPY', type: 'call', strike: 500, exp: '2026-09-18' };
  it('renders contract history + Net Premium', () => {
    render(<ChartModal row={row} open history={[{ date: '2026-09-01', premium: 50000 }]} netPremiumSeries={[{ label: '2026-09-01', value: 100000 }]} onClose={() => {}} />);
    expect(screen.getByTestId('chart-modal')).toBeInTheDocument();
    expect(screen.getByTestId('chart-history')).toBeInTheDocument();
    expect(screen.getByTestId('chart-netprem')).toBeInTheDocument();
  });
  it('honest empty when no history (not fixture mode)', () => {
    render(<ChartModal row={row} open history={[]} netPremiumSeries={[]} onClose={() => {}} />);
    expect(screen.getByTestId('chart-history-empty').textContent).toMatch(/No history yet/);
    expect(screen.getByTestId('chart-netprem-empty').textContent).toMatch(/No premium series yet/);
  });
  it('checklist 6 steps checkable + verdict', () => {
    render(<ChartModal row={row} open history={[]} netPremiumSeries={[]} onClose={() => {}} />);
    const check0 = screen.getByTestId('check-0');
    fireEvent.click(check0);
    expect(check0.checked).toBe(true);
    fireEvent.click(screen.getByTestId('verdict-confirmed'));
    expect(screen.getByTestId('verdict-label').textContent).toBe('confirmed');
  });
  it('null when closed', () => {
    const { container } = render(<ChartModal row={row} open={false} onClose={() => {}} />);
    expect(container.textContent).toBe('');
  });
});
