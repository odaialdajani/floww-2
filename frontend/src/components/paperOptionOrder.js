import { effectiveOptionPrice } from "./tradeMath";

const SINGLE_LEG_STRATEGIES = {
  buy_call: { side: "buy", optionType: "call", quoteSource: "ask", quoteField: "call_ask" },
  buy_put: { side: "buy", optionType: "put", quoteSource: "ask", quoteField: "put_ask" },
  sell_call: { side: "sell", optionType: "call", quoteSource: "bid", quoteField: "call_bid" },
  sell_put: { side: "sell", optionType: "put", quoteSource: "bid", quoteField: "put_bid" },
};

const positivePrice = (value) => {
  const price = Number(value);
  return Number.isFinite(price) && price > 0 ? price : null;
};

function parseOsiOptionSymbol(value) {
  const match = String(value ?? "").trim().toUpperCase().match(/^([A-Z][A-Z0-9 .-]{0,5})(\d{6})([CP])(\d{8})$/);
  if (!match) return null;
  return { root: match[1].replace(/[^A-Z0-9]/g, ""), expiry: match[2], right: match[3], strike: Number(match[4]) / 1000 };
}

function normalizedTicker(value) {
  return String(value ?? "").replace(/^\^/, "").toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function matchesOsiTicket(symbol, trade, optionType) {
  const parsed = parseOsiOptionSymbol(symbol);
  if (!parsed || parsed.right !== (optionType === "call" ? "C" : "P")) return false;
  if (normalizedTicker(trade.ticker) !== parsed.root) return false;
  const strike = Number(trade.strike);
  if (!Number.isFinite(strike) || Math.round(strike * 1000) !== Math.round(parsed.strike * 1000)) return false;
  const dateMatch = String(trade.expiry ?? "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!dateMatch) return false;
  const expiry = `${dateMatch[1].slice(-2)}${dateMatch[2]}${dateMatch[3]}`;
  if (expiry !== parsed.expiry) return false;
  return true;
}

/** Resolve only an explicit positive limit or the executable quote side. */
export function resolvePaperOptionOrder({ strategy, selection, limitPrice }) {
  const contract = SINGLE_LEG_STRATEGIES[strategy];
  if (!contract || !selection) return null;

  const hasEnteredLimit = String(limitPrice ?? "").trim() !== "";
  const explicitLimit = positivePrice(limitPrice);
  if (hasEnteredLimit && explicitLimit === null) return null;
  if (explicitLimit !== null) {
    return { ...contract, limitPrice: explicitLimit, priceSource: "limit", orderType: "limit" };
  }

  const quote = effectiveOptionPrice(selection, strategy, "");
  if (quote.source !== contract.quoteSource || positivePrice(quote.price) === null) return null;
  return { ...contract, limitPrice: positivePrice(quote.price), priceSource: quote.source, orderType: "limit" };
}

/** Revalidate the panel payload before App builds a paper-order request. */
export function buildPaperOptionOrderRequest(trade) {
  const contract = SINGLE_LEG_STRATEGIES[trade?.strategy];
  if (!contract || !trade?.oi_symbol || trade.orderType !== "limit") return null;
  if (trade.orderSide !== contract.side || trade.optionType !== contract.optionType) return null;
  if (!matchesOsiTicket(trade.oi_symbol, trade, contract.optionType)) return null;

  const price = positivePrice(trade.orderLimitPrice);
  if (price === null) return null;
  if (trade.priceSource === "limit") {
    if (positivePrice(trade.limitPrice) !== price) return null;
  } else {
    if (trade.priceSource !== contract.quoteSource) return null;
    if (positivePrice(trade[contract.quoteField]) !== price) return null;
  }

  const quantity = Number(trade.quantity);
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 100) return null;
  return {
    symbol: trade.oi_symbol,
    qty: String(quantity),
    side: contract.side,
    order_type: "limit",
    limit_price: String(price),
  };
}
