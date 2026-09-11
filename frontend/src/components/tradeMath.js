// Pure trade-math helpers — extracted from TradeJournal/QuickTradePanel so the
// money logic is unit-tested. Fixes from the 2026-07-11 wide audit:
//  - a trade closed at $0 (total loss) must count as CLOSED, not open, so its
//    loss isn't silently erased from P&L/win-rate.
//  - breakeven (scratch) trades are neither win nor loss.
//  - option strategy risk/reward must reflect the actual strategy, not a naive
//    "buy → defined risk / else Unlimited" split, and never render "$NaN".

// Closed if it has an exit date OR any non-empty exit price ("0" included —
// that's a total loss, the case the old exit_price>0 test wrongly dropped).
export function isTradeClosed(t) {
  const hasDate = t.exit_date != null && String(t.exit_date).trim() !== "";
  const hasPrice = t.exit_price != null && String(t.exit_price).trim() !== "";
  return hasDate || hasPrice;
}

// Realized P&L in dollars. exit_price "" → 0 (total loss). Longs gain when
// exit>entry; shorts invert.
export function tradePnl(t) {
  const entry = parseFloat(t.entry_price) || 0;
  const exit = parseFloat(t.exit_price) || 0;
  const qty = parseInt(t.quantity) || 1;
  return (exit - entry) * qty * 100 * (t.action === "buy" ? 1 : -1);
}

// "win" | "loss" | "scratch" — scratch (exit === entry) is excluded from both
// so it doesn't drag win-rate down or dilute avg-loss.
export function tradeOutcome(t) {
  const entry = parseFloat(t.entry_price) || 0;
  const exit = parseFloat(t.exit_price) || 0;
  if (exit === entry) return "scratch";
  const favorable = t.action === "buy" ? exit > entry : exit < entry;
  return favorable ? "win" : "loss";
}

const money = (n) => `$${Math.round(n).toLocaleString()}`;

// Mid of one option leg — REFERENCE ONLY (CBOE/IBKR: mid is never a fill
// promise). Prefers (bid+ask)/2, then last/midpoint, then whichever side
// exists. NaN when nothing is quoted (far-OTM SOFI case).
export function contractMid(c) {
  if (!c || typeof c !== "object") return NaN;
  const bid = Number(c.bid);
  const ask = Number(c.ask);
  const last = Number(c.last ?? c.midpoint);
  if (Number.isFinite(bid) && Number.isFinite(ask) && bid > 0 && ask > 0) {
    return (bid + ask) / 2;
  }
  if (Number.isFinite(last) && last > 0) return last;
  if (Number.isFinite(bid) && bid > 0) return bid;
  if (Number.isFinite(ask) && ask > 0) return ask;
  return NaN;
}

// Raw leg quotes as finite-or-NaN {bid, ask, last}.
export function legQuote(selection, side) {
  const s = selection || {};
  const p = side === "call"
    ? { bid: s.call_bid, ask: s.call_ask, last: s.call_last }
    : { bid: s.put_bid, ask: s.put_ask, last: s.put_last };
  const num = (v) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : NaN;
  };
  return { bid: num(p.bid), ask: num(p.ask), last: num(p.last) };
}

// Side-aware executable-side price (industry standard: buys lift the ask,
// sells hit the bid). Falls back to mid/last reference when the
// executable side is missing. Returns {price, source}.
export function legPrice(selection, side, action) {
  const { bid, ask, last } = legQuote(selection, side);
  const want = action === "sell" ? bid : ask;   // executable side first
  if (Number.isFinite(want)) {
    return { price: want, source: action === "sell" ? "bid" : "ask" };
  }
  const mid = contractMid({ bid, ask, last });
  if (Number.isFinite(mid)) return { price: mid, source: "mid" };
  return { price: NaN, source: "none" };
}

function ivEstimate(selection) {
  const spot = Number(selection?.spot);
  const iv = Number(selection?.iv);
  if (Number.isFinite(spot) && Number.isFinite(iv) && spot > 0 && iv > 0) {
    return spot * iv * 0.01;
  }
  return NaN;
}

// Effective per-share premium for the ticket, with source for the UI.
// Priority: limit override > side-aware executable side (buys at ask,
// sells at bid) > mid/last reference > IV estimate > NaN.
// Straddle sums both legs' buy-sides. Iron condor needs wings (see
// condorCredit): credit field/limit, else NaN — never a single-leg guess.
export function effectiveOptionPrice(selection, strategy, limitOverride, wings) {
  const lim = Number(limitOverride);
  if (Number.isFinite(lim) && lim > 0) return { price: lim, source: "limit" };
  if (strategy === "straddle") {
    const c = legPrice(selection, "call", "buy");
    const p = legPrice(selection, "put", "buy");
    if (Number.isFinite(c.price) && Number.isFinite(p.price)) {
      const bothAsk = c.source === "ask" && p.source === "ask";
      return { price: c.price + p.price, source: bothAsk ? "ask-sum" : "ref-sum" };
    }
  } else if (strategy === "iron_condor") {
    const credit = condorCredit(wings);
    if (Number.isFinite(credit) && credit > 0) return { price: credit, source: "credit" };
    return { price: NaN, source: "none" };
  } else if (strategy === "buy_call") {
    const r = legPrice(selection, "call", "buy");
    if (Number.isFinite(r.price)) return r;
  } else if (strategy === "sell_call") {
    const r = legPrice(selection, "call", "sell");
    if (Number.isFinite(r.price)) return r;
  } else if (strategy === "buy_put") {
    const r = legPrice(selection, "put", "buy");
    if (Number.isFinite(r.price)) return r;
  } else if (strategy === "sell_put") {
    const r = legPrice(selection, "put", "sell");
    if (Number.isFinite(r.price)) return r;
  }
  const iv = ivEstimate(selection);
  if (Number.isFinite(iv)) return { price: iv, source: "iv" };
  return { price: NaN, source: "none" };
}

// Expected condor credit from the wing subform (user-typed credit wins;
// rien de plus — wings alone carry no quotes to net against each other).
export function condorCredit(wings) {
  const c = Number(wings?.credit);
  return Number.isFinite(c) && c > 0 ? c : NaN;
}

// Narrowest condor wing width from wing strikes, or NaN.
export function condorWidth(wings) {
  const n = (v) => Number(v);
  const putW = n(wings?.put_short) - n(wings?.put_long);
  const callW = n(wings?.call_long) - n(wings?.call_short);
  const widths = [putW, callW].filter((w) => Number.isFinite(w) && w > 0);
  return widths.length ? Math.min(...widths) : NaN;
}

// Notional display: never "$0" on a missing price (the SOFI bug).
export function formatNotional(price, quantity) {
  const px = Number(price);
  const q = parseInt(quantity) || 0;
  if (!Number.isFinite(px) || q <= 0) return "—";
  return money(px * q * 100);
}

// Shared journal key — MUST match TradeJournal + TradeAnalytics.
export const JOURNAL_STORAGE_KEY = "floww_trades_v2";

const TICKET_STRATEGY_MAP = {
  buy_call: { type: "call", action: "buy", setup: "BUY CALL" },
  buy_put: { type: "put", action: "buy", setup: "BUY PUT" },
  sell_call: { type: "call", action: "sell", setup: "SELL CALL" },
  sell_put: { type: "put", action: "sell", setup: "SELL PUT" },
  straddle: { type: "call", action: "buy", setup: "STRADDLE" },
  iron_condor: { type: "call", action: "sell", setup: "IRON CONDOR" },
};

// Ticket -> TradeJournal-shaped entries. One entry per ticket (multi-leg
// strategies collapse with the strategy in `setup` — never fabricate legs).
// Missing price journals with entry_price "" (open, unknown) — a ticket is
// never dropped: the drop was the "trades vanish" bug.
export function ticketToJournalEntries(ticket) {
  const t = ticket || {};
  const m = TICKET_STRATEGY_MAP[t.strategy] || { type: "call", action: "buy", setup: String(t.strategy || "SINGLE").toUpperCase() };
  const px = Number(t.effectivePrice);
  const w = t.wings || null;
  const legDetail = w && t.strategy === "iron_condor"
    ? ` wings P ${w.put_long ?? "—"}/${w.put_short ?? "—"} C ${w.call_short ?? "—"}/${w.call_long ?? "—"} credit ${w.credit ?? t.effectivePrice ?? "—"}`
    : "";
  const entry = {
    ticker: String(t.ticker || "").replace("^", "").toUpperCase(),
    type: m.type,
    action: m.action,
    strike: t.strike ?? "",
    expiry: t.expiry ?? "",
    quantity: String(t.quantity ?? 1),
    entry_price: Number.isFinite(px) && px > 0 ? px : "",
    exit_price: "",
    entry_date: (t.timestamp || new Date().toISOString()).slice(0, 10),
    exit_date: "",
    notes: `Quick trade @ spot ${t.spot ?? "—"}${t.priceSource ? ` (${t.priceSource} price)` : ""}${legDetail}`,
    gex_regime: "",
    setup: m.setup,
    tags: "quick-trade",
    source: "quick-trade",
  };
  return [entry];
}

// ─── TradeEntry idea -> journal (issue #17) ────────────────────────────────
// TradeEntry "Save Trade Idea" rows live in component state only and vanish
// on unmount. This mapper converts one idea (template + form data) into a
// TradeJournal-shaped entry for the shared `floww_trades_v2` store so the
// idea survives remount/reload and renders in TradeJournal + TradeAnalytics.
// One entry per idea (multi-leg templates collapse with legs itemized in
// `notes` — never fabricate legs). contracts -> quantity, regime ->
// gex_regime, strikes/credit/debit/premium -> notes/setup. Missing price
// journals as "" (open, unknown) — an idea is never dropped. Extra display
// keys (template/templateName/spot/source) ride along; journal consumers
// ignore unknown keys, TradeEntry uses them to rebuild its in-session list.

const IDEA_TEMPLATE_MAP = {
  iron_condor: { type: "call", action: "sell", setup: "IRON CONDOR" },
  long_straddle: { type: "call", action: "buy", setup: "STRADDLE" },
  call_spread: { type: "call", action: "buy", setup: "BULL CALL SPREAD" },
  put_spread: { type: "put", action: "buy", setup: "BEAR PUT SPREAD" },
};

export function tradeIdeaToJournalEntries(idea) {
  const t = idea || {};
  const d = t.data || {};
  const template = t.template || "single_leg";
  const priceOrBlank = (v) => {
    const n = Number(v);
    return Number.isFinite(n) && n > 0 ? n : "";
  };
  const at = `@ spot ${t.spot ?? "—"}`;
  let type = "call", action = "buy", setup = template.toUpperCase();
  let strike = "", entry_price = "", notes = "";
  if (template === "iron_condor") {
    const m = IDEA_TEMPLATE_MAP.iron_condor;
    type = m.type; action = m.action; setup = m.setup;
    strike = d.call_short ?? d.put_short ?? "";
    entry_price = priceOrBlank(d.credit);
    notes = `Iron Condor P ${d.put_long ?? "—"}/${d.put_short ?? "—"}`
      + ` C ${d.call_short ?? "—"}/${d.call_long ?? "—"}`
      + ` credit ${d.credit ?? "—"} ${at}`;
  } else if (template === "long_straddle") {
    const m = IDEA_TEMPLATE_MAP.long_straddle;
    type = m.type; action = m.action; setup = m.setup;
    strike = d.strike ?? "";
    const cp = Number(d.call_premium), pp = Number(d.put_premium);
    const parts = [cp, pp].filter((n) => Number.isFinite(n) && n > 0);
    entry_price = parts.length ? parts.reduce((a, b) => a + b, 0) : "";
    notes = `Long Straddle strike ${d.strike ?? "—"}`
      + ` call premium ${d.call_premium ?? "—"}`
      + ` put premium ${d.put_premium ?? "—"} ${at}`;
  } else if (template === "call_spread" || template === "put_spread") {
    const m = IDEA_TEMPLATE_MAP[template];
    type = m.type; action = m.action; setup = m.setup;
    strike = d.long_strike ?? "";
    entry_price = priceOrBlank(d.debit);
    const label = template === "call_spread" ? "Bull Call Spread" : "Bear Put Spread";
    notes = `${label} long ${d.long_strike ?? "—"}`
      + ` short ${d.short_strike ?? "—"} debit ${d.debit ?? "—"} ${at}`;
  } else if (template === "single_leg") {
    const a = String(d.action || "");
    type = /put/i.test(a) ? "put" : "call";
    action = /sell/i.test(a) ? "sell" : "buy";
    setup = a ? a.toUpperCase() : "SINGLE";
    strike = d.strike ?? "";
    entry_price = priceOrBlank(d.premium);
    notes = `${a || "Single leg"} strike ${d.strike ?? "—"}`
      + ` premium ${d.premium ?? "—"} ${at}`;
  } else {
    const detail = Object.entries(d).map(([k, v]) => `${k} ${v}`).join(" ");
    notes = `${t.templateName || template} ${detail} ${at}`.trim();
  }
  return [{
    ticker: String(t.ticker || "").replace("^", "").toUpperCase(),
    type,
    action,
    strike,
    expiry: "",
    quantity: String(d.contracts ?? 1),
    entry_price,
    exit_price: "",
    entry_date: (t.timestamp || new Date().toISOString()).slice(0, 10),
    exit_date: "",
    notes,
    gex_regime: t.regime || "",
    setup,
    tags: "trade-entry",
    // Display extras (ignored by journal consumers; TradeEntry hydrates its
    // in-session list from these after unmount/remount).
    source: "trade-entry",
    template,
    templateName: t.templateName || template,
    spot: t.spot ?? null,
  }];
}

// Max risk / reward display strings for an option strategy. estPrice is the
// per-share premium estimate (may be non-finite when IV is missing → "—").
// Correct at the strategy-category level; long debit trades have DEFINED risk
// (premium paid), short naked calls have unlimited risk, condors are defined
// both sides.
export function strategyRiskReward(strategy, estPrice, quantity, strike, wings) {
  const q = parseInt(quantity) || 1;
  const px = Number(estPrice);
  if (!Number.isFinite(px)) return { maxRisk: "—", maxReward: "—" };
  if (strategy === "iron_condor") {
    // Defined both sides once wings are known: risk = narrowest wing
    // minus credit, reward = credit. Without wings keep the honest label.
    const width = condorWidth(wings);
    if (Number.isFinite(width)) {
      return { maxRisk: money(Math.max(0, width - px) * q * 100), maxReward: money(px * q * 100) };
    }
    return { maxRisk: "Defined", maxReward: money(px * q * 100) };
  }
  const premium = px * q * 100;                       // debit paid / credit received
  const bounded = Number.isFinite(Number(strike))
    ? Math.max(0, (Number(strike) - px) * q * 100)    // long put profit / short put assignment risk
    : null;
  const boundedStr = bounded == null ? "Defined" : money(bounded);
  switch (strategy) {
    case "buy_call":
    case "straddle":                                   // long: pay premium, unbounded upside
      return { maxRisk: money(premium), maxReward: "Unlimited" };
    case "buy_put":
      return { maxRisk: money(premium), maxReward: boundedStr };
    case "sell_call":                                  // naked short call: unbounded risk
      return { maxRisk: "Unlimited", maxReward: money(premium) };
    case "sell_put":
      return { maxRisk: boundedStr, maxReward: money(premium) };
    default:
      return { maxRisk: money(premium), maxReward: "Unlimited" };
  }
}
