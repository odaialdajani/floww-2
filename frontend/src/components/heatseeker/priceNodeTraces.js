// Each overlay segment belongs only to the candle for which it was known.
// Never bridge gaps or project the last observed node backwards in time.
export function priceNodeTraces(frames = []) {
  const candles = {
    type: "candlestick", name: "Price", x: frames.map(f => f.time),
    open: frames.map(f => f.open), high: frames.map(f => f.high),
    low: frames.map(f => f.low), close: frames.map(f => f.close),
    increasing: { line: { color: "#62cdb4" } }, decreasing: { line: { color: "#e58a91" } },
  };
  const x = [], y = [], text = [];
  frames.forEach((frame, i) => {
    const at = Date.parse(frame.time);
    const duration = Math.min(frame.duration_seconds || 60, Math.max(0, 900 - (frame.node_age_seconds || 0))) * 1000;
    const next = i + 1 < frames.length ? Date.parse(frames[i + 1].time) : at + duration;
    if (!Number.isFinite(at)) return;
    const end = new Date(Math.min(at + duration, next)).toISOString();
    (frame.nodes || []).forEach(node => {
      if (!Number.isFinite(node.level) || node.level <= 0) return;
      x.push(frame.time, end, null);
      y.push(node.level, node.level, null);
      const label = `Saved node ${node.level.toFixed(2)}<br>Known at ${frame.nodes_known_at}`;
      text.push(label, label, null);
    });
  });
  return [candles, { type: "scatter", mode: "lines", name: "Recorded nodes", x, y, text,
    hovertemplate: "%{text}<extra></extra>", connectgaps: false,
    line: { color: "#e4bd72", width: 2 } }];
}
