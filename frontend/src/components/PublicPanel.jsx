import React, { useCallback, useEffect, useState } from "react";
import { API } from "../config/api";
import { storedAppKeyHeaders } from "../utils/appKey";

const numberOrNull = value => {
  if (value === null || value === undefined || typeof value === "boolean" || (typeof value === "string" && !value.trim())) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};
const fmtMoney = value => {
  const number = numberOrNull(value);
  return number === null ? "Unavailable" : number.toLocaleString("en-US", {style: "currency", currency: "USD"});
};
const fmtPercent = value => {
  const number = numberOrNull(value);
  return number === null ? "Unavailable" : number.toFixed(2) + "%";
};
const completeTotal = (rows, key) => {
  const values = rows.map(row => numberOrNull(row[key]));
  return values.every(value => value !== null) ? numberOrNull(values.reduce((sum, value) => sum + value, 0)) : null;
};

/**
 * PublicPanel — Public.com brokerage tab (account + portfolio + orders).
 *
 * Rebuilt 2026-09-04: the prior WIP file was deleted uncommitted, which
 * broke the production build (App.js statically imports this module).
 * This version talks only to the verified live endpoints:
 *   GET /api/public/account
 *   GET /api/public/portfolio
 *   GET /api/public/orders
 * States: loading / error (key missing, API down) / empty / ready.
 * Polls every 30s while mounted.
 */
export default function PublicPanel() {
  const [account, setAccount] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [orders, setOrders] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async (signal) => {
    try {
      // Brokerage reads require the backend master key. Never prompt here
      // (this polls every 30s) — show the key-missing hint instead.
      const headers = storedAppKeyHeaders();
      if (!headers) throw new Error("APP_KEY_MISSING");
      const [a, p, o] = await Promise.all(
        ["account", "portfolio", "orders"].map((k) =>
          fetch(`${API}/public/${k}`, { signal, headers }).then((r) => {
            if (r.status === 401 || r.status === 503) throw new Error("APP_KEY_REJECTED");
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
          })
        )
      );
      setAccount(a);
      setPortfolio(p);
      setOrders(o);
      setError(null);
    } catch (e) {
      if (e?.name === "AbortError") return;
      setError(e?.message || "Brokerage unavailable");
    }
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    const id = setInterval(() => load(ctrl.signal), 30000);
    return () => { ctrl.abort(); clearInterval(id); };
  }, [load]);

  if (error && !account && !portfolio) {
    return (
      <div className="panel p-4" data-testid="public-panel-error">
        <div className="label">Public Broker</div>
        <div className="text-sm" style={{ color: "var(--neg)" }}>
          {error === "APP_KEY_MISSING" || error === "APP_KEY_REJECTED"
            ? "Backend key missing or rejected. Enter API_SECRET_KEY once (any mutating action prompts), then retry."
            : `Brokerage unreachable (${error}). Set PUBLIC_API_KEY on the backend, then retry.`}
        </div>
        <button className="btn mt-2" onClick={() => load(new AbortController().signal)}>Retry</button>
      </div>
    );
  }
  if (!account && !portfolio) {
    return (
      <div className="panel p-4" data-testid="public-panel-loading">
        <div className="label">Public Broker</div>
        <div className="text-sm text-slate-500">Loading brokerage…</div>
      </div>
    );
  }

  const positions = portfolio?.positions || [];
  const orderList = orders?.orders || [];
  const assetGroups = new Map();
  positions.forEach(position => {
    const type = position.asset_type || "UNKNOWN";
    if (!assetGroups.has(type)) assetGroups.set(type, []);
    assetGroups.get(type).push(position);
  });
  return (
    <div className="panel p-4 space-y-3" data-testid="public-panel">
      <div className="label">Public Broker · {account?.account_id || "—"}</div>
      {error && <p role="status">Refresh failed. Showing the last received account data.</p>}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[12px] mono">
        <div><div className="label">Cash</div><div>{fmtMoney(portfolio ? portfolio.cash : account?.cash)}</div></div>
        <div><div className="label">Buying power</div><div>{fmtMoney(portfolio ? portfolio.buying_power : account?.buying_power)}</div></div>
        <div><div className="label">Portfolio value</div><div>{fmtMoney(portfolio?.portfolio_value)}</div></div>
        <div><div className="label">Positions</div><div>{portfolio?.position_count ?? positions.length}</div></div>
      </div>
      <div>
        <div className="label mb-1">Positions{positions.length ? ` (${positions.length})` : ""}</div>
        {positions.length === 0 ? (
          <div className="text-[12px] text-slate-500">No positions.</div>
        ) : (
          <div style={{overflowX: "auto"}}>
          <table className="w-full text-[12px] mono" style={{minWidth: 900}} aria-label="Broker positions">
            <thead><tr><th align="left">Symbol</th><th align="left">Asset type</th><th align="right">Qty</th><th align="right">Price</th><th align="right">Market value</th><th align="right">Cost basis</th><th align="right">P&amp;L</th><th align="right">Day gain</th><th align="right">Total gain</th></tr></thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={p.symbol || i}>
                  <td>{p.symbol}</td><td>{p.asset_type || "Unknown"}</td>
                  <td align="right">{numberOrNull(p.quantity) ?? "Unavailable"}</td>
                  <td align="right">{fmtMoney(p.current_price)}</td>
                  <td align="right">{fmtMoney(p.market_value)}</td>
                  <td align="right">{fmtMoney(p.cost_basis)}</td>
                  <td align="right">{fmtMoney(p.pnl)}</td>
                  <td align="right">{fmtPercent(p.day_gain_pct)}</td>
                  <td align="right">{fmtPercent(p.total_gain_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
      {assetGroups.size > 0 && <section aria-label="Holdings by asset type" className="space-y-2">
        <div className="label">Holdings by asset type</div>
        {[...assetGroups].map(([type, rows]) => <div key={type} className="text-[12px] mono">
          <strong>{type}</strong> · {rows.length} positions · Value: <span aria-label={type + " total market value"}>{fmtMoney(completeTotal(rows, "market_value"))}</span>
          {" · Cost: "}<span aria-label={type + " total cost"}>{fmtMoney(completeTotal(rows, "cost_basis"))}</span>
          {" · P&L: "}<span aria-label={type + " total profit and loss"}>{fmtMoney(completeTotal(rows, "pnl"))}</span>
        </div>)}
      </section>}
      <div>
        <div className="label mb-1">Orders{orderList.length ? ` (${orderList.length})` : ""}</div>
        {orderList.length === 0 ? (
          <div className="text-[12px] text-slate-500">No orders.</div>
        ) : (
          <table className="w-full text-[12px] mono">
            <thead><tr><th align="left">Symbol</th><th align="left">Side</th><th align="right">Qty</th><th align="left">Status</th></tr></thead>
            <tbody>
              {orderList.slice(0, 25).map((o, i) => (
                <tr key={o.order_id || i}>
                  <td>{o.symbol}</td>
                  <td>{o.side}</td>
                  <td align="right">{o.quantity}</td>
                  <td>{o.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
