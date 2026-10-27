// B21 — the options-destination navigation regression pin (the independent
// helper's before-freeze finding): every intent that NAMES the options desk as
// its destination must arrive at a VISIBLE desk on the fresh Stock study
// (deskOpen starts false, chart focus may be on) — the Saved reading, the
// Range-return and the Options-desk toggle. Deliberate hiding stays its own
// action. The real-pixel VISIBILITY proof runs in the live browser pass;
// these pins hold the state machine honest in jsdom.
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SkylitDashboard from '../../SkylitDashboard';

jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock('../../RangeAnalyticsWorkspace', () => () => <div data-testid="range-workspace" />);
jest.mock('../../AskFlow', () => () => <div data-testid="askflow-panel" />);
jest.mock('../../SavedChartReadings', () => ({ onOpen, disabled }) => (
  disabled ? null : <button type="button" data-testid="saved-readings-open" onClick={() => onOpen('r1')}>Saved readings</button>
));

const desk = () => document.querySelector('[aria-label="SPY options desk"]');
const switchBtn = () => screen.getAllByTestId('skylit-study-switch').find(b => (b.textContent || '').trim());

const deskHidden = () => { const d = desk(); return !d || d.hasAttribute('hidden'); };

test('fresh Stock: the desk is hidden; the Saved-reading intent arrives at a VISIBLE desk', async () => {
  const axios = require('axios');
  window.localStorage.clear();
  axios.get.mockImplementation(async () => ({ data: {} }));
  render(<SkylitDashboard ticker="SPY" defaultStudy="chart" />);
  await waitFor(() => expect(switchBtn()).toBeInTheDocument());
  expect(desk()).not.toBeNull();
  expect(deskHidden()).toBe(true); // the deliberate destination — hidden by default
  fireEvent.click(screen.getByTestId('saved-readings-open'));
  await waitFor(() => expect(deskHidden()).toBe(false));
});
