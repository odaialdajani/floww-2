// Wave-2 mounted-surface receipt test: PriceNodeHistory plumbs the panel's
// alertLines accept (server-owned alert display lines onto the price chart
// via RecordedPriceChart's existing renderer). Data comes from the caller
// only — the panel invents nothing.
jest.setTimeout(12000);
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn(), all: jest.fn((xs) => Promise.all(xs)) }));

const React = require('react');
const axios = require('axios');
const { default: PriceNodeHistory } = require('../../PriceNodeHistory');
const { render, screen, waitFor, fireEvent } = require('@testing-library/react');

const frames2 = [
  { time: '2026-09-10T14:00:00+00:00', open: 100.5, high: 101.0, low: 99.5, close: 100.75 },
  { time: '2026-09-10T14:01:00+00:00', open: 100.75, high: 103.3, low: 98.7, close: 103.0 },
];

beforeEach(() => {
  axios.get.mockImplementation(async () => ({ data: { ticker: 'SPY', frames: frames2, candles_with_recorded_nodes: 0, scopes: [] } }));
});

test('panel forwards supplied alertLines into the chart renderer; absent by default', async () => {
  // Baseline: no alert lines are rendered when the prop is not supplied.
  const base = render(React.createElement(PriceNodeHistory, { ticker: 'SPY', open: true }));
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
  expect(screen.queryByTestId('alert-line')).not.toBeInTheDocument();
  base.unmount();

  // Supplied in-range armed and stale alerts render through the panel plumbing.
  render(React.createElement(PriceNodeHistory, {
    ticker: 'SPY', open: true,
    alertLines: [{ id: 'w2armed', price: 101.5, state: 'armed' }, { id: 'w2stale', price: 100.2, state: 'stale' }],
  }));
  await waitFor(() => expect(screen.getByTestId('recorded-price-chart')).toBeInTheDocument());
  const lines = screen.getAllByTestId('alert-line');
  expect(lines).toHaveLength(2);
  const armed = lines.find((l) => l.getAttribute('data-state') === 'armed');
  const stale = lines.find((l) => l.getAttribute('data-state') === 'stale');
  expect(armed).toBeTruthy();
  expect(stale).toBeTruthy();
  // Stale lines explicitly refuse evaluation with an honest note.
  expect(screen.getByText(/Stale alert refused/)).toBeInTheDocument();
  fireEvent.pointerMove(screen.getByTestId('recorded-price-chart'));
});
