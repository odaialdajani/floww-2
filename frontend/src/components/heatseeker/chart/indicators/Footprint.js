// B22 footprint primitives mirror: CVD and footprint come only from
// classified buy/sell trade sizes; unclassified volume stays its own number;
// a session boundary re-zeros the running delta; a later corrected
// restatement replaces its original statement; candle direction is never a
// stand-in for classified flow; and a disabled capability renders the whole
// read unavailable rather than a proxy. Mirrors backend/services/chart_delta.py.

export const CAPABILITIES = { classified_sizes: true };

// Candle direction is explicitly not classified trade flow: no pseudo-CVD.
export function candleDelta() {
  return {
    status: "unavailable",
    reason: "candle direction is not classified trade flow; CVD needs classified buy/sell sizes",
  };
}

export function sessionCvd(bars, { capabilities = CAPABILITIES } = {}) {
  if (capabilities.classified_sizes !== true) {
    return { status: "unavailable", reason: "capability disabled: classified_sizes", rows: [] };
  }
  const list = Array.isArray(bars) ? bars : [];
  const keyOf = (b) => (b != null && b.time != null ? String(b.time) : null);
  const superseded = new Set(
    list.filter((b) => b && b.corrected === true && b.time != null).map(keyOf)
  );
  const stream = list.filter((b) => b
    && typeof b.buy === "number"
    && typeof b.sell === "number"
    && !(b.corrected !== true && keyOf(b) != null && superseded.has(keyOf(b))));
  if (!list.length || !stream.length) {
    return { status: "unknown", reason: "no classified bars", rows: [] };
  }
  let running = 0;
  const rows = [];
  for (const bar of stream) {
    if (bar.session_reset === true) running = 0;
    const open = running;
    running += bar.buy - bar.sell;
    rows.push({
      open,
      close: running,
      delta: bar.buy - bar.sell,
      unclassified: typeof bar.unclassified === "number" ? bar.unclassified : 0,
      time: bar.time != null ? bar.time : null,
    });
  }
  return { status: "ok", rows };
}

// One footprint cell: classified sizes only; an unclassified remainder is
// reported as its own number and never distributed into buy or sell.
export function footprintCell(bar) {
  if (!bar || typeof bar !== "object"
    || typeof bar.buy !== "number" || typeof bar.sell !== "number") {
    return { status: "unknown", reason: "no classified sizes for this bar" };
  }
  return {
    status: "ok",
    buy: bar.buy,
    sell: bar.sell,
    net: bar.buy - bar.sell,
    unclassified: typeof bar.unclassified === "number" ? bar.unclassified : 0,
  };
}
