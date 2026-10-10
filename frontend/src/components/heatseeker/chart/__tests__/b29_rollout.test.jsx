import { FLAGS, isNewChartEnabled, setChartV1, killSwitch } from '../workspaceFlags';
test('canary defaults incumbent + reversible kill switch', () => {
  setChartV1(false);
  expect(FLAGS.chartV1).toBe(false);
  expect(isNewChartEnabled()).toBe(false);
  setChartV1(true);
  const receipt = killSwitch();
  expect(receipt).toEqual({ reverted: true, dataLoss: false });
  expect(isNewChartEnabled()).toBe(false);
});
