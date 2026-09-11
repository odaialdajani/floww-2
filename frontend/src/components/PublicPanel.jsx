import React, { useCallback, useEffect, useState } from "react";
import { API } from "../config/api";

const fmtMoney = (v) => {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("en-US", { style: "currency", currency: "USD" });
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
      const [a, p, o] = await Promise.all(
        ["account", "portfolio", "orders"].map((k) =>
          fetch(`${API}/public/${k}`, { signal }).then((r) => {
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
          Brokerage unreachable ({error}). Set PUBLIC_API_KEY on the backend, then retry.
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
  return (
    <div className="panel p-4 space-y-3" data-testid="public-panel">
      <div className="label">Public Broker · {account?.account_id || "—"}</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[12px] mono">
        <div><div className="label">Cash</div><div>{fmtMoney(portfolio?.cash ?? account?.cash)}</div></div>
        <div><div className="label">Buying power</div><div>{fmtMoney(portfolio?.buying_power ?? account?.buying_power)}</div></div>
        <div><div className="label">Portfolio value</div><div>{fmtMoney(portfolio?.portfolio_value)}</div></div>
        <div><div className="label">Positions</div><div>{portfolio?.position_count ?? positions.length}</div></div>
      </div>
      <div>
        <div className="label mb-1">Positions{positions.length ? ` (${positions.length})` : ""}</div>
        {positions.length === 0 ? (
          <div className="text-[12px] text-slate-500">No positions.</div>
        ) : (
          <table className="w-full text-[12px] mono">
            <thead><tr><th align="left">Symbol</th><th align="right">Qty</th><th align="right">Price</th><th align="right">P&amp;L</th></tr></thead>
            <tbody>
              {positions.slice(0, 25).map((p, i) => (
                <tr key={p.symbol || i}>
                  <td>{p.symbol}</td>
                  <td align="right">{p.quantity}</td>
                  <td align="right">{fmtMoney(p.current_price)}</td>
                  <td align="right">{fmtMoney(p.pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
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
