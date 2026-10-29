// B21 dark-pool print level mirrors: exact single prints only, equities
// only, largest by notional, and direction is always unknown because the
// feed never proves a side inside the dark pool. Aggregated or summary
// notional is never presented as a single print, and a later correction
// replaces the print it corrects. Mirrors backend/services/chart_darkpool.py
// with explicit delay/correction eligibility added.

const REQUIRED_FIELDS = ["price", "size", "event_time", "venue"];

export function isExactEquityPrint(p) {
  if (!p || typeof p !== "object") return false;
  if ((p.asset_class == null ? "equity" : p.asset_class) !== "equity") return false;
  if (p.aggregate === true) return false;
  return REQUIRED_FIELDS.every((k) => p[k] !== null && p[k] !== undefined);
}

// Prints eligible for level display: exact equity prints that a later
// correction has not replaced, and — when a delay cap is enforced — only
// prints with a known delay inside the cap.
export function eligiblePrints(prints, { maxDelaySeconds = null } = {}) {
  const list = (prints || []).filter((p) => p && typeof p === "object");
  const superseded = new Set(
    list.filter((p) => p && p.correction_of != null).map((p) => p.correction_of)
  );
  return list.filter((p) => {
    if (!isExactEquityPrint(p)) return false;
    if (superseded.has(p.print_id)) return false;
    if (maxDelaySeconds == null) return true;
    if (!Number.isFinite(Number(p.delay_seconds))) return false;
    return Number(p.delay_seconds) <= maxDelaySeconds;
  });
}

export function topLevels(prints, opts = {}) {
  const topN = opts == null || opts.topN == null ? 3 : opts.topN;
  const rows = eligiblePrints(prints, opts);
  const sorted = [...rows].sort((a, b) => (b.price * b.size) - (a.price * a.size));
  return sorted.slice(0, Math.max(0, topN)).map((p) => ({
    price: p.price,
    size: p.size,
    venue: p.venue,
    event_time: p.event_time,
    notional: p.price * p.size,
    direction: "unknown",
  }));
}

// Display string keeps every unknown explicit.
export function levelLabel(level) {
  if (!level || !Number.isFinite(Number(level.price))) return "Print unknown";
  return [
    `${level.price} × ${level.size}`,
    `venue ${level.venue}`,
    `notional ${level.notional}`,
    "direction unknown",
  ].join(" · ");
}
