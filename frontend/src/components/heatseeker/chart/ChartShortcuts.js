// B27 shortcuts/usability: never inside typing fields, focus/escape, touch replay
// above chips, two auto-fit modes, watermarks for source/proxy/replay.
export function shouldHandleShortcut(event) {
  const tag = event?.target?.tagName;
  return tag !== 'INPUT' && tag !== 'TEXTAREA';
}
export const FIT_MODES = ['fit-visible', 'fit-all'];
export function watermark({ source, proxy, replay }) {
  const parts = [];
  if (source) parts.push(`source:${source}`);
  if (proxy) parts.push(`proxy:${proxy}`);
  if (replay) parts.push('replay');
  return parts.join(' ');
}
