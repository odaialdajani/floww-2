// Read only the immutable evidence saved with this answer, never the current UI.
const finite = value => typeof value === "number" && Number.isFinite(value);
const price = value => `$${value.toLocaleString("en-US", {maximumFractionDigits: 6})}`;
function amount(value) {
  const size = Math.abs(value);
  if (size > 0 && size < 0.01) return `${value > 0 ? "+" : ""}${String(value)}`;
  const [scale, suffix] = size >= 1e9 ? [1e9, "B"] : size >= 1e6 ? [1e6, "M"] : size >= 1e3 ? [1e3, "K"] : [1, ""];
  return `${value > 0 ? "+" : ""}${(value / scale).toLocaleString("en-US", {maximumFractionDigits: 2})}${suffix}`;
}
const unique = values => values.length === 1 ? values[0] : null;
const sameScope = (left, right) => left.snapshot_id === right.snapshot_id && left.horizon === right.horizon;

export function readableScopeText(text = "") {
  return String(text)
    .replace(/\bmap:[a-f0-9]{64}\b/g, "whole chart")
    .replace(/\bdisplay:[a-f0-9]{64}\b/g, "visible chart");
}

export function savedChartReading(answer, ticker) {
  const facts = (answer?.facts || []).filter(f => f?.ticker === ticker);
  const strikes = unique(facts.filter(f => f.metric === "Displayed strikes"));
  if (!strikes?.snapshot_id || !Array.isArray(strikes.value) || !strikes.value.length ||
      !strikes.value.every(s => finite(s) && s > 0) || new Set(strikes.value).size !== strikes.value.length) return null;
  const display = metric => unique(facts.filter(f => f.metric === metric && sameScope(f, strikes)));
  const whole = metric => unique(facts.filter(f => f.metric === metric && f.snapshot_id === strikes.snapshot_id));
  const expiry = display("Displayed expiry dates");
  if (!Array.isArray(expiry?.value) || !expiry.value.length ||
      !expiry.value.every(e => typeof e === "string" && /^\d{4}-\d{2}-\d{2}$/.test(e))) return null;
  const lines = [];
  const add = (text, supporting) => lines.push({text, factIds: supporting.map(f => f.id)});
  add(`${strikes.value.length} strikes · ${expiry.value.length} expiries: ${expiry.value.join(", ")}.`, [strikes, expiry]);
  const cell = display("Selected display cell");
  const parts = typeof cell?.contract === "string" ? cell.contract.split(":") : [];
  const expectedUnit = ["gex", "skylit"].includes(parts[2]) ? "display gamma units" : `display ${parts[2]} units`;
  if (parts.length === 3 && finite(cell.value) && strikes.value.includes(Number(parts[1])) &&
      expiry.value.includes(parts[0]) && ["gex", "skylit", "vex", "charm"].includes(parts[2]) && cell.unit === expectedUnit) {
    const measure = {gex: "gamma", skylit: "gamma", vex: "vanna", charm: "charm"}[parts[2]];
    add(`Selected cell: ${ticker} ${price(Number(parts[1]))} · ${parts[0]} · ${amount(cell.value)} displayed ${measure}.`, [cell, strikes, expiry]);
    add("This is the chart's estimate for that strike and expiry, not an observed dealer position.", [cell]);
  }
  const bars = display("Displayed net gamma");
  if (Array.isArray(bars?.value) && bars.value.length === strikes.value.length && bars.unit === "display gamma units") {
    const known = bars.value.map((value, index) => ({value, strike: strikes.value[index]})).filter(row => finite(row.value));
    const complete = known.length === bars.value.length;
    if (known.length) {
      const maximum = Math.max(...known.map(row => Math.abs(row.value)));
      if (maximum === 0) add(complete ? "All visible bars are zero; no largest level stands out." : "All complete visible bars are zero; missing bars remain unknown.", [bars]);
      else {
        const largest = known.filter(row => Math.abs(row.value) === maximum);
        const label = complete ? "Largest visible bar" : "Largest complete visible bar";
        add(`${label}${largest.length > 1 ? "s (tied)" : ""}: ${largest.map(row => `${price(row.strike)} at ${amount(row.value)} displayed gamma`).join("; ")}.`, [strikes, bars]);
        add("This marks the strongest concentration by bar size in the saved chart; it is not a price target or a direction forecast.", [bars]);
      }
      if (!complete) add("Missing bars could change which level is largest; a complete total is unavailable.", [bars]);
      const total = display("Displayed total gamma");
      const sum = known.reduce((value, row) => value + row.value, 0);
      if (complete && finite(total?.value) && total.unit === bars.unit &&
          Math.abs(sum - total.value) <= Math.max(1, Math.abs(sum)) * 1e-10) {
        add(`Visible total: ${amount(total.value)} displayed gamma across the saved strikes and expiries.`, [total, bars, strikes, expiry]);
      }
      add("Bars add the shown expiries at each strike. The cumulative line adds those bars from lower to higher strikes.", [strikes, bars, expiry]);
    }
  }
  const flip = whole("Displayed flip");
  if (finite(flip?.value) && flip.value > 0 && flip.unit === "USD") {
    add(`Whole-chart flip: ${price(flip.value)}. It estimates where net gamma changes sign; it is not recalculated for the selected cell or visible rows.`, [flip]);
  }
  const quote = whole("Cached map price");
  if (finite(quote?.value) && quote.value > 0 && quote.unit === "USD") {
    add(`Price saved with this chart: ${price(quote.value)}${quote.status === "stale" ? " (already stale when saved)" : ""}.`, [quote]);
  }
  const used = new Set(lines.flatMap(line => line.factIds));
  const usedFacts = facts.filter(f => used.has(f.id));
  const chartFacts = usedFacts.filter(f => f.metric !== "Cached map price");
  if (chartFacts.some(f => !f.event_time)) {
    add("Market observation time is unknown. These values explain the saved chart; they do not establish current market conditions.", [strikes, expiry]);
  } else if (usedFacts.some(f => f.status !== "ok")) {
    add("Some readings were stale or limited when saved. They explain that snapshot, not current market conditions.", [strikes, expiry]);
  } else {
    add(`Saved market observation: ${strikes.event_time}. These readings may have changed since.`, [strikes]);
  }
  return lines;
}
