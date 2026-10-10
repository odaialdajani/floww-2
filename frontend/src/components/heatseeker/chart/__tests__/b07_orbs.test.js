import { rankOrbs, isVanna } from '../primitives/ExposureOrbs';
const N = (strike, v, status = 'ok') => ({ strike, signed_value: v, status });
test('signed king, P25 inclusive, tie strike asc', () => {
  const out = rankOrbs([N(100, -100), N(105, 50), N(110, 25)], { pThreshold: 25 });
  expect(out.king.strike).toBe(100);
  expect(out.ranked.map((n) => n.strike)).toEqual([100, 105, 110]);
});
test('tie breaks by strike ascending', () => {
  const out = rankOrbs([N(110, 50), N(100, -50)]);
  expect(out.ranked[0].strike).toBe(100);
});
test('zero vs unavailable + incomplete disables full', () => {
  expect(rankOrbs([{ strike: 1, signed_value: 0 }]).reason).toBe('measured-zero');
  expect(rankOrbs([]).reason).toBe('unavailable');
  expect(rankOrbs([N(1, 10), { strike: 2, signed_value: 5, status: 'incomplete' }]).reason).toBe('incomplete-full-scope');
  const sub = rankOrbs([N(1, 10)], { scopeIdentity: 'observed-subset' });
  expect(sub.reason).toBe('ok');
});
test('VANNA triple identity only', () => {
  expect(isVanna({ model: 'VEX_1VOLPT', basis: 'local-bs-vanna.v1', unit: 'USD-per-volpt' })).toBe(true);
  expect(isVanna({ model: 'vex_surface', basis: 'gex.v2', unit: 'S1' })).toBe(false);
  expect(isVanna({ model: 'VEX_1VOLPT' })).toBe(false);
});
