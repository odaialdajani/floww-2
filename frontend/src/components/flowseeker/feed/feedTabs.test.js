import { validateTabs } from './feedTabs.js';

describe('feedTabs validate', () => {
  it('live max 10', () => {
    expect(validateTabs(Array(10).fill({}), 'live').valid).toBe(true);
    expect(validateTabs(Array(11).fill({}), 'live').valid).toBe(false);
  });
  it('scanner max 5', () => {
    expect(validateTabs(Array(5).fill({}), 'scanner').valid).toBe(true);
    expect(validateTabs(Array(6).fill({}), 'scanner').valid).toBe(false);
  });
});
