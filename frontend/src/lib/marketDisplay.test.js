import {formatStrike,formatGreek} from './marketDisplay';
test('preserves fractional strikes and unknowns',()=>{expect(formatStrike(257.5)).toBe('257.5');expect(formatStrike(null)).toBe('—');expect(formatStrike(Infinity)).toBe('—');});
test('small known Greeks cannot round to a false zero',()=>{expect(formatGreek(.002)).toBe('0.0020');expect(formatGreek(-.0000003)).toBe('-3.00e-7');expect(formatGreek(0)).toBe('0');expect(formatGreek(null)).toBe('—');});
