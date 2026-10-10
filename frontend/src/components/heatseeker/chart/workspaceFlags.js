// B29 rollout: incumbent default, reversible kill switch, no data loss.
export const FLAGS = { chartV1: false };
export function isNewChartEnabled() { return FLAGS.chartV1 === true; }
export function setChartV1(on) { FLAGS.chartV1 = on === true; }
export function killSwitch() { FLAGS.chartV1 = false; return { reverted: true, dataLoss: false }; }
