import { projectionExtent, buildProjection } from '../primitives/ProjectionZones';
test('projection is scenario whitespace, no future records', () => {
  expect(projectionExtent({ intervalMinutes: 5, periods: 6 })).toBe(30);
  const out = buildProjection({ eligiblePositioning: { zones: [1] }, intervalMinutes: 5 });
  expect(out.status).toBe('scenario');
  expect(out.forecast).toBe(false);
  expect(buildProjection({}).status).toBe('unavailable');
});
