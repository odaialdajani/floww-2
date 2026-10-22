import React from "react";

// B20 filtered premium flow: call premium sums up, put premium renders down,
// unclassified sides stay explicitly unknown, and drilldown shares the exact
// filter/cursor hash identity of the totals row so the two can only agree
// when they describe the same bucket. Sides come from classified feed tags
// only; ask ticks are never used to infer buy direction.
// Mirrors backend/services/chart_flow.py bucket algebra.

// R21-03 caller binding (H3 gates): the flow window key must come from the
// OWNING chart resolution — never a hardcoded '1m' while the chart runs 30m.
// Unknown resolutions stay honestly unmapped, never guessed.
export function flowWindowKeyFor(barSeconds) {
  const map = { 60: "1m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h" };
  return map[Number(barSeconds)] || null;
}

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
  envelope = null,
  barId = null,
  windowKey = "1m",
  filters = {},
  hash = null,
  cursorHash = null,
  onBucketClick = null,
}) {
  // R21-03 caller binding: the server admission envelope (admit_flow_bucket)
  // is the source of truth when present — a refusal renders its named code,
  // an unavailable bucket renders its reason and named gap counts, and an
  // available bucket shows the SERVER-admitted totals with its gap and
  // certification basis. Totals are never re-derived locally from the
  // envelope; the legacy trades path below stays for trades-only callers.
  if (envelope && typeof envelope === "object") {
    const gapRows = Object.entries(envelope.gaps && typeof envelope.gaps === "object" ? envelope.gaps : {})
      .filter(([, n]) => Number(n) > 0)
      .map(([k, n]) => `${k} ${n}`);
    const gapsBlock = gapRows.length ? (
      <div data-testid="flow-gaps" role="status">
        Excluded rows: {gapRows.join(" \u00b7 ")} \u2014 named gaps, never folded into totals.
      </div>
    ) : null;
    if (envelope.status === "refused") {
      return (
        <div className="flow-pane" data-testid="flow-pane-refused" data-reason={String(envelope.reason || "refused")}>
          Flow refused \u2014 {String(envelope.reason || "unspecified refusal")}.
        </div>
      );
    }
    if (envelope.status !== "available" || !envelope.totals) {
      return (
        <div className="flow-pane" data-testid="flow-pane-unavailable" data-reason={String(envelope.reason || "unavailable")}>
          Flow unavailable \u2014 {String(envelope.reason || "no admitted rows for this flow bucket")}.
          {gapsBlock}
        </div>
      );
    }
    const et = envelope.totals;
    const sameScope = typeof cursorHash === "string" && cursorHash === envelope.scope_hash;
    return (
      <div className="flow-pane" data-testid="flow-pane">
        <div data-testid="flow-totals">
          <span data-testid="flow-call-premium">Call premium up {fmt(et.call_premium)}</span>
          <span data-testid="flow-put-premium">Put premium down {fmt(et.put_premium)}</span>
          <span data-testid="flow-unknown">
            Unknown {et.unknown} of {et.count} \u2014 not classified by the feed
          </span>
        </div>
        {gapsBlock}
        <div data-testid="flow-certification" role="status">
          {(envelope.certification && envelope.certification.basis) || "row-level eligibility"};
          hash-certified: {String((envelope.certification && envelope.certification.certified_by_hash) || false)}.
        </div>
        <ul data-testid="flow-top">
          {(et.top || []).map((tr, i) => (
            <li key={`${tr.group_id || "leg"}-${i}`} data-testid={`flow-top-${i}`}>
              {tr.side || "unknown"}
              {" \u00b7 "}
              {fmt(Number(tr.premium) || 0)}
              {tr.leg_count > 1 ? ` \u00b7 ${tr.leg_count} legs (net ${fmt(tr.net_premium)})` : ""}
            </li>
          ))}
        </ul>
        {sameScope ? (
          <div data-testid="flow-drilldown">
            <span data-testid="flow-drilldown-call">Call premium up {fmt(et.call_premium)}</span>
            <span data-testid="flow-drilldown-put">Put premium down {fmt(et.put_premium)}</span>
            <span data-testid="flow-drilldown-unknown">
              Unknown {et.unknown} of {et.count}
            </span>
          </div>
        ) : (
          <div data-testid="flow-drilldown-scope-note" role="status">
            Drilldown scope differs from the totals bucket {String(envelope.scope_hash || "unknown")} \u2014 not merged.
          </div>
        )}
        {onBucketClick && (
          <button type="button" data-testid="flow-open-drilldown" onClick={() => onBucketClick({ hash: envelope.scope_hash })}>
            Open bucket drilldown
          </button>
        )}
      </div>
    );
  }
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
