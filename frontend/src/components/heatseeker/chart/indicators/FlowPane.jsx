import React from "react";

// B20 filtered premium flow: call premium sums up, put premium renders down,
// unclassified sides stay explicitly unknown, and drilldown shares the exact
// filter/cursor hash identity of the totals row so the two can only agree
// when they describe the same bucket. Sides come from classified feed tags
// only; ask ticks are never used to infer buy direction.
// Mirrors backend/services/chart_flow.py bucket algebra.

// Stable local bucket identity: server-provided hashes pass straight
// through; otherwise a deterministic sorted-string digest keeps drilldown
// and totals on the same identity without re-deriving the backend digest.
export function bucketHash(barId, windowKey, filters, serverHash = null) {
  if (typeof serverHash === "string" && serverHash) return serverHash;
  const stable = (value) => {
    if (value === null || typeof value !== "object") return JSON.stringify(value ?? null);
    if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
    return `{${Object.keys(value).sort().map((k) => `${JSON.stringify(k)}:${stable(value[k])}`).join(",")}}`;
  };
  const raw = stable({ bar: barId, window: windowKey, filters: filters || {} });
  let hash = 0x811c9dc5;
  for (let i = 0; i < raw.length; i += 1) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

// Call premium above zero, put premium as negative, unclassified counted
// and never folded into either side.
export function bucketize(trades) {
  const list = Array.isArray(trades) ? trades : [];
  let call = 0, put = 0, unknown = 0;
  for (const t of list) {
    if (!t || typeof t !== "object") { unknown += 1; continue; }
    const premium = Number(t.premium);
    const value = Number.isFinite(premium) ? premium : 0;
    if (t.side === "call") call += value;
    else if (t.side === "put") put += value;
    else unknown += 1;
  }
  return {
    call_premium: call,
    put_premium: -Math.abs(put),
    count: list.length,
    unknown,
    top: [...list]
      .filter((t) => t && typeof t === "object")
      .sort((a, b) => (Number(b.premium) || 0) - (Number(a.premium) || 0))
      .slice(0, 3),
  };
}

// Economic multi-leg grouping: legs sharing a group id form one ticket with
// one economic side; a mixed-direction ticket stays its own explicit class
// and is never re-labeled into call-up or put-down.
export function groupLegs(trades) {
  const list = Array.isArray(trades) ? trades : [];
  const groups = new Map();
  const singles = [];
  for (const t of list) {
    if (t && typeof t === "object" && t.group_id != null) {
      const group = groups.get(t.group_id) || { group_id: t.group_id, legs: [] };
      group.legs.push(t);
      groups.set(t.group_id, group);
    } else {
      singles.push(t);
    }
  }
  const tickets = [...groups.values()].map((group) => {
    const sides = new Set(group.legs.map((t) => t.side));
    const singleSide = sides.size === 1 ? [...sides][0] : "mixed";
    const net = group.legs.reduce(
      (sum, t) => sum + (Number(t.premium) || 0) * (t.side === "put" ? -1 : 1),
      0
    );
    return { ...group, side: singleSide, leg_count: group.legs.length, net_premium: net };
  });
  return { tickets, singles, groups: groups.size };
}

// Bucketable units: single legs stay as-is and same-side multi-leg tickets
// act as one economic unit; mixed tickets pass unchanged and land in the
// explicit unknown class (their legs never split into call and put).
export function bucketUnits(trades) {
  const { tickets, singles } = groupLegs(trades);
  return [
    ...tickets.map((t) => (t.side === "mixed" ? t : { ...t, premium: t.net_premium })),
    ...singles,
  ];
}

const fmt = (n) => (Number.isFinite(n) ? `${Math.round(n * 100) / 100}` : "unknown");

export default function FlowPane({
  trades = null,
  barId = null,
  windowKey = "1m",
  filters = {},
  hash = null,
  cursorHash = null,
  onBucketClick = null,
}) {
  if (!Array.isArray(trades)) {
    return (
      <div className="flow-pane" data-testid="flow-pane-unavailable">
        Flow unknown — no trades published for this bucket.
      </div>
    );
  }
  const totals = bucketize(bucketUnits(trades));
  const totalsHash = bucketHash(barId, windowKey, filters, hash);
  const sameScope = typeof cursorHash === "string" && cursorHash === totalsHash;
  const drilldown = sameScope ? totals : null;

  return (
    <div className="flow-pane" data-testid="flow-pane">
      <div data-testid="flow-totals">
        <span data-testid="flow-call-premium">Call premium up {fmt(totals.call_premium)}</span>
        <span data-testid="flow-put-premium">Put premium down {fmt(totals.put_premium)}</span>
        <span data-testid="flow-unknown">
          Unknown {totals.unknown} of {totals.count} — not classified by the feed
        </span>
      </div>
      {totals.unknown > 0 && (
        <div data-testid="flow-unknown-note" role="status">
          Unclassified trades are excluded from both sides; the feed never guesses a side from an ask tick.
        </div>
      )}
      <ul data-testid="flow-top">
        {totals.top.map((t, i) => (
          <li key={`${t.group_id || "leg"}-${i}`} data-testid={`flow-top-${i}`}>
            {t.side || "unknown"}
            {" · "}
            {fmt(Number(t.premium) || 0)}
            {t.leg_count > 1 ? ` · ${t.leg_count} legs (net ${fmt(t.net_premium)})` : ""}
          </li>
        ))}
      </ul>
      {sameScope ? (
        <div data-testid="flow-drilldown">
          <span data-testid="flow-drilldown-call">Call premium up {fmt(drilldown.call_premium)}</span>
          <span data-testid="flow-drilldown-put">Put premium down {fmt(drilldown.put_premium)}</span>
          <span data-testid="flow-drilldown-unknown">
            Unknown {drilldown.unknown} of {drilldown.count}
          </span>
        </div>
      ) : (
        <div data-testid="flow-drilldown-scope-note" role="status">
          Drilldown scope differs from the totals bucket {totalsHash || "unknown"} — not merged.
        </div>
      )}
      {onBucketClick && (
        <button type="button" data-testid="flow-open-drilldown" onClick={() => onBucketClick({ hash: totalsHash })}>
          Open bucket drilldown
        </button>
      )}
    </div>
  );
}
