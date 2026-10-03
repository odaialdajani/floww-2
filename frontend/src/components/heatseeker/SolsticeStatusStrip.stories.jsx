import { expect, fn, userEvent, within } from 'storybook/test';
import SolsticeStatusStrip from './SolsticeStatusStrip';

const wall = { wall_id: 'storybook-wall', low: 590, high: 595 };
const snapshot = {
  metrics: { nearest_walls: [wall], nearest_by_side: { below: wall } },
  gamma_regime_v1: { sign: 'positive' },
  exposure_basis: 'OI',
  quality: { state: 'usable', setupEligible: true },
};

export default {
  title: 'Solstice/Status Strip',
  component: SolsticeStatusStrip,
  parameters: {
    docs: { description: { component: 'Snapshot-derived market status. Fixtures are synthetic; they do not fetch data or authorize trading. WAIT is a valid state, and degraded data must remain visible.' } },
  },
  args: { ticker: 'SPY', spot: 592, isLive: true, data: snapshot, onSelectWall: fn() },
};

export const Usable = {
  async play({ canvasElement, args }) {
    const canvas = within(canvasElement);
    await expect(canvas.getByTestId('solstice-data')).toHaveTextContent('Data usable');
    await userEvent.click(canvas.getByRole('button', { name: 'below 590–595' }));
    await expect(args.onSelectWall).toHaveBeenCalledWith(wall);
  },
};

export const Waiting = {
  args: { data: { ...snapshot, quality: { state: 'partial', setupEligible: false, reasonCodes: ['OPTIONS_DATA_INCOMPLETE'] } } },
  async play({ canvasElement }) {
    await expect(within(canvasElement).getByTestId('solstice-setup')).toHaveTextContent('Wait — OPTIONS_DATA_INCOMPLETE');
  },
};

export const Degraded = {
  args: { data: null, spot: null, isLive: false },
  async play({ canvasElement }) {
    await expect(within(canvasElement).getByTestId('solstice-data')).toHaveTextContent('Data degraded/unknown');
  },
};

export const SessionBlocked = {
  args: { data: { ...snapshot, session: { entry_allowed: false, reasons: ['OUTSIDE_SESSION'] } } },
  async play({ canvasElement }) {
    await expect(within(canvasElement).getByTestId('solstice-setup')).toHaveTextContent('Wait — OUTSIDE_SESSION');
  },
};
