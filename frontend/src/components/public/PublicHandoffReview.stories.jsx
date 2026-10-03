import React from 'react';
import { expect, userEvent, within } from 'storybook/test';
import PublicHandoffReview from './PublicHandoffReview';

// Synthetic admitted research shape, not a broker/market/activation receipt.
const selection = { page: 'trinity', ticker: 'SPY', snapshotId: 'story-record', selectedWall: 'story-wall', selectedExpiry: '2026-10-02', selectedContract: { osi: 'SPY261002C00500000' }, displayMode: 'live' };
const turn = { turn_id: 'story-turn', status: 'completed', answer: { context: selection, plan_draft: {
  version: 'trade-plan-draft.v1', draft_id: 'story-draft', created_at: '2026-10-02T14:45:00Z', correlation_id: 'story-turn', context_hash: 'a'.repeat(64),
  evidence_ids: ['story-evidence'], observation_ids: ['story-record'], executable: false,
  contract: { osi: selection.selectedContract.osi, strike: '500', expiry: '2026-10-02', type: 'call', snapshot_id: 'story-record', bid: 1, ask: 1.1 },
} } };
export default { title: 'Public/Manual reviewed handoff', component: PublicHandoffReview, args: { selection, turn, grounded: true },
  decorators: [Story => <div style={{maxWidth: 390, padding: 16, background: '#0d222a'}}><Story/></div>],
  parameters: { docs: { description: { component: 'Fixture-backed, disarmed production component. Copy and operator reporting never establish broker delivery, permission or activation.' } } } };
export const WaitingForOwner = {};
export const MissingExactContract = { args: { turn: null, grounded: false } };
export const NativeBrief = { async play({canvasElement}) {
  const c=within(canvasElement);
  await userEvent.selectOptions(c.getByLabelText('Execution owner'), 'PUBLIC_NATIVE_AGENT');
  await userEvent.click(c.getByRole('button', {name:'Prepare dated brief'}));
  await expect(c.getByLabelText('Editable Public brief').value).toContain('Premium budget: UNSET');
} };
export const BackendBlocked = { async play({canvasElement}) {
  const c=within(canvasElement);
  await userEvent.selectOptions(c.getByLabelText('Execution owner'), 'FLOWW_BACKEND');
  await expect(c.getByRole('button', {name:'Prepare dated brief'})).toBeDisabled();
} };
export const PreviousSelection = { args: { selection: {...selection, selectedWall: 'different-wall'} } };
