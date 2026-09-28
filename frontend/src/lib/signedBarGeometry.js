/** Pure signed bar geometry for OpenCode handoff (Command Code C1.3).

No React, DOM, screenshots, or chart library. Given one shared numeric
range and one value, return the CSS-plan geometry every renderer must obey:
negative values render on the negative side of zero, positive values on the
positive side, with zero-line placement derived from the same range.
*/

function signedBarGeometry(value, lo, hi) {
  const span = hi - lo || 1;
  const height = (Math.abs(value) / span) * 100;
  const zeroFromBottom = ((0 - lo) / span) * 100;
  const positive = value >= 0;
  const bottom = positive ? zeroFromBottom : zeroFromBottom - height;
  return { height, bottom, positive, zeroFromBottom };
}

function zeroLineVisible(lo, hi) {
  return lo < 0 && hi > 0;
}

module.exports = { signedBarGeometry, zeroLineVisible };
