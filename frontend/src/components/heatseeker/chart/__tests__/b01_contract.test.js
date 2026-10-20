/**
 * B01 canonical contract — frontend mirror + MOUNTED consumer proof.
 * Mirrors backend/tests/chart/test_b01_contract.py fixtures exactly, then
 * proves the strict grammar actually gates the visible Stock chart's data
 * path (checkedCandles), not just the helper module.
 */
import {parsePrice, parseVolume, legacyCloseForTrinity, vwapCaption, barIsComplete, revisionIsRecorded} from '../chartContract';
import {checkedCandles} from '../../recordedPriceChartData';

const good = {time:'2026-10-06T14:00:00Z', open:100, high:102, low:99, close:101};

test('B01: booleans, blanks and nonfinite never become prices; zero volume is real, unknown stays dropped', () => {
  expect(parsePrice(true)).toBeNull();
  expect(parsePrice(false)).toBeNull();
  expect(parseVolume(true)).toBeNull();
  expect(parseVolume(false)).toBeNull();
  expect(parsePrice(null)).toBeNull();
  expect(parsePrice('')).toBeNull();
  expect(parsePrice('   ')).toBeNull();
  expect(parsePrice([])).toBeNull();
  expect(parsePrice({})).toBeNull();
  expect(parsePrice(NaN)).toBeNull();
  expect(parsePrice(Infinity)).toBeNull();
  expect(parseVolume(null)).toBeNull();
  expect(parseVolume('')).toBeNull();
  expect(parseVolume(NaN)).toBeNull();
  expect(parseVolume(Infinity)).toBeNull();
  // Genuine zero volume preserved as a real reading; missing stays unknown.
  expect(parseVolume(0)).toBe(0);
  expect(parseVolume('0')).toBe(0);
  expect(parseVolume(null)).toBeNull();
  // Valid numeric strings accepted only by the explicit grammar.
  expect(parsePrice('123.45')).toBe(123.45);
  expect(parsePrice('  123.45  ')).toBe(123.45);
  expect(parsePrice('abc')).toBeNull();
  expect(parsePrice('12a')).toBeNull();
  // Prices positive; volume nonnegative.
  expect(parsePrice(0)).toBeNull();
  expect(parsePrice(-5)).toBeNull();
  expect(parseVolume(-1)).toBeNull();
  expect(parsePrice(100.5)).toBe(100.5);
});

test('B01 mounted: checkedCandles enforces the strict grammar — boolean prices are rejected, never coerced', () => {
  const boolHigh = {...good, time:'2026-10-06T14:05:00Z', high:true};
  const stringClose = {...good, time:'2026-10-06T14:10:00Z', close:'101.5'};
  const out = checkedCandles([good, boolHigh, stringClose]);
  expect(out).toHaveLength(2);
  expect(out[0]).toEqual(good);
  expect(out[1].close).toBe(101.5);
  expect(typeof out[1].close).toBe('number');
});

test('B01 mounted: zero volume is preserved; unknown and string volumes stay absent — never substituted as zero', () => {
  const zero = {...good, volume:0};
  const unknown = {...good, time:'2026-10-06T14:05:00Z', volume:null};
  const asString = {...good, time:'2026-10-06T14:10:00Z', volume:'10'};
  const out = checkedCandles([zero, unknown, asString]);
  expect(out[0].volume).toBe(0);
  expect('volume' in out[1]).toBe(false);
  // Pinned by the accepted integrity fixture: a string volume stays
  // unavailable at the mounted consumer rather than inventing a reading.
  expect('volume' in out[2]).toBe(false);
});

test('B01 legacy Trinity contract: frames[].close keeps its old shape; VWAP unavailable without a qualified source', () => {
  expect(legacyCloseForTrinity({close:100.0})).toBe(100.0);
  expect(legacyCloseForTrinity({close:null})).toBeNull();
  expect(legacyCloseForTrinity({})).toBeNull();
  expect(legacyCloseForTrinity({close:true})).toBeNull();
  expect(vwapCaption(null)).toBe('unavailable VWAP');
  expect(vwapCaption(NaN)).toBe('unavailable VWAP');
  expect(vwapCaption(123.456)).toBe('VWAP 123.46');
});

test('B01 temporal bounds: completed bars need end<=cursor; an inferred end never proves recorded availability', () => {
  expect(barIsComplete(100, 100)).toBe(true);
  expect(barIsComplete(101, 100)).toBe(false);
  expect(revisionIsRecorded('recorded', 90, 100)).toBe(true);
  expect(revisionIsRecorded('inferred_bar_end', 90, 100)).toBe(false);
  expect(revisionIsRecorded('unknown', 90, 100)).toBe(false);
  expect(revisionIsRecorded('recorded', 110, 100)).toBe(false);
});
