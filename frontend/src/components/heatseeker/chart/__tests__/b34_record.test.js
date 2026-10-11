import { awaitRecording } from '../pollRecording';
test('resolves true on first scopes sighting, false after tries run out', async () => {
  let calls = 0;
  const hit = await awaitRecording(async () => (++calls >= 3 ? { scopes: ['s'] } : { scopes: [] }), { tries: 4, gapMs: 5 });
  expect(hit).toEqual({ recorded: true, tries: 3 });
  expect(calls).toBe(3);
  calls = 0;
  const miss = await awaitRecording(async () => { calls += 1; return { scopes: [] }; }, { tries: 2, gapMs: 5 });
  expect(miss).toEqual({ recorded: false, tries: 2 });
  expect(calls).toBe(2);
});
test('fetch errors count as misses, never throw', async () => {
  const out = await awaitRecording(async () => { throw new Error('down'); }, { tries: 2, gapMs: 5 });
  expect(out).toEqual({ recorded: false, tries: 2 });
});
