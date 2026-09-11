import React, { useEffect, useRef, useState } from "react";
import { BACKEND_URL } from "../../config/api";

const API = `${BACKEND_URL}/api/flowseeker`;
const object = (value) => value && typeof value === "object" && !Array.isArray(value);
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const count = (value) => Number.isInteger(value) && value >= 0 ? value : "unknown";
const percent = (value) => finite(value) && value >= 0 && value <= 1 ? `${Math.round(value * 100)}%` : "Unavailable";
const points = (value) => finite(value) && Math.abs(value) <= 1 ? `${value > 0 ? "+" : ""}${Math.round(value * 100)} pp` : "Unavailable";
const interval = (value, formatter) => Array.isArray(value) && value.length === 2 && value.every(finite) && value[0] <= value[1]
  ? `${formatter(value[0])} to ${formatter(value[1])}` : "Unavailable";
const dateText = (value) => typeof value === "string" && Number.isFinite(Date.parse(value)) ? value : "unknown";
const initial = { status: "idle", data: null };

export default function OutcomeLedger({ active = true }) {
  const [open, setOpen] = useState(false);
  const [outcomes, setOutcomes] = useState(initial);
  const [model, setModel] = useState(initial);
  const pending = useRef(null);
  const sequence = useRef(0);

  useEffect(() => {
    if (!active) {
      sequence.current += 1;
      pending.current?.abort();
      setOutcomes((s) => s.status === "loading" ? { ...initial, status: "unavailable" } : s);
      setModel((s) => s.status === "loading" ? { ...initial, status: "unavailable" } : s);
    }
    return () => { sequence.current += 1; pending.current?.abort(); };
  }, [active]);

  const load = () => {
    if (!active) return;
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    const id = ++sequence.current;
    setOpen(true);
    setOutcomes({ ...initial, status: "loading" });
    setModel({ ...initial, status: "loading" });
    const request = async (path, valid, update) => {
      let timer;
      try {
        const timeout = new Promise((_, reject) => {
          timer = setTimeout(() => { controller.abort(); reject(new Error("timeout")); }, 15000);
        });
        const data = await Promise.race([
          fetch(`${API}${path}`, { signal: controller.signal }).then(async (response) => {
            if (!response.ok) {
              const failure = await response.json().catch(() => null);
              throw new Error(typeof failure?.detail === "string" && failure.detail.includes("Public-only") ? "public-only" : "unavailable");
            }
            const body = await response.json();
            if (!object(body) || body.ok !== true || !valid(body)) throw new Error("invalid response");
            return body;
          }),
          timeout,
        ]);
        if (id === sequence.current) update({ status: "ready", data });
      } catch (error) {
        if (id === sequence.current) update({ ...initial, status: "unavailable", reason: error?.message === "public-only" ? "public-only" : null });
      } finally { clearTimeout(timer); }
    };
    void request("/outcomes?days=60", (body) => object(body.per_rule), setOutcomes);
    void request("/model", (body) => Number.isInteger(body.stage) && body.stage >= 0, setModel);
  };

  const rows = Object.entries(outcomes.data?.per_rule || {}).filter(([, value]) => object(value));
  const data = outcomes.data;
  const fitted = model.data;
  const minimum = Number.isInteger(data?.min_alerts) && data.min_alerts > 0 ? data.min_alerts : 5;
  return (
    <section aria-label="Historical outcome ledger" style={{ marginTop: 20 }}>
      <button type="button" className="th-chipb" aria-expanded={open} disabled={!active}
        onClick={() => open ? setOpen(false) : load()}>
        {open ? "Hide Outcome Ledger" : "Outcome Ledger - load history and recalculate estimate"}
      </button>
      <p className="th-meta">Legacy alert history uses yfinance daily prices and is unavailable in Public-only mode. Where legacy sources are allowed, loading may recalculate a local statistical estimate; these are not live Public readings or proven future results.</p>
      {open && <div>
        <button type="button" className="th-chipb" disabled={!active || outcomes.status === "loading" || model.status === "loading"} onClick={load}>Reload history and recalculate estimate</button>
        {outcomes.status === "loading" && <p role="status">Loading historical outcomes...</p>}
        {outcomes.status === "unavailable" && <p role="status">{outcomes.reason === "public-only" ? "Historical outcomes unavailable in Public-only mode. No legacy history was read or recalculated." : "Historical outcomes unavailable. No performance figures are shown."}</p>}
        {outcomes.status === "ready" && <>
          <p className="th-meta">Source: {data.source === "cron" ? "saved historical calculation" : data.source === "live" ? "calculated on request from historical prices" : "historical ledger; calculation source unknown"}. Calculation time: {dateText(data.computed_at || data.updated_at || data.asof)}. Market observation time: unknown.</p>
          <p>History window: {count(data.lookback_days)} days. Hit: a move in either direction of at least {finite(data.sigma_k) && data.sigma_k > 0 ? data.sigma_k : "unknown"} times prior daily volatility over {count(data.horizon_sessions)} sessions. The legacy calculation uses a 1% move when volatility is missing. This measures move size, not whether the alert got direction right, and differs from the 30-day conviction results above.</p>
          {rows.length === 0 ? <p>No measured rule history is available yet.</p> : <div className="th-tbl">
            <table aria-label="Historical rule outcomes">
              <thead><tr>{["Rule", "Measured / excluded", "Hit rate", "Matched comparison", "Difference", "95% interval", "Median best / worst move"].map((label) => <th key={label} style={{ cursor: "default" }}>{label}</th>)}</tr></thead>
              <tbody>{rows.map(([rule, s]) => {
                const thin = s.uncalibrated !== false || !Number.isInteger(s.n_measured) || s.n_measured < minimum;
                return <tr key={rule}>
                  <td>{rule}{(s.decayed || s.status === "AMBER") && <strong> - Review: recent results weakened</strong>}</td>
                  <td>{count(s.n_measured)} / {count(s.n_censored)}</td>
                  <td>{thin ? `Too few to judge (need ${minimum})` : percent(s.precision)}</td>
                  <td>{thin ? "Too few to judge" : `${percent(s.control_rate)} (n ${count(s.n_controls)})`}</td>
                  <td>{thin ? "Unavailable" : points(s.lift)}</td>
                  <td>{thin ? "Unavailable" : Array.isArray(s.lift_ci) ? `Difference: ${interval(s.lift_ci, points)}` : `Hit rate: ${interval(s.precision_ci, percent)}`}</td>
                  <td>{thin ? "Unavailable" : `${finite(s.median_mfe_sigma) ? s.median_mfe_sigma : "unknown"} / ${finite(s.median_mae_sigma) ? s.median_mae_sigma : "unknown"} times prior volatility`}</td>
                </tr>;
              })}</tbody>
            </table>
          </div>}
          {object(data.overall) && <p>
            Overall: {Number.isInteger(data.overall.n_measured) && data.overall.n_measured >= minimum ? percent(data.overall.precision) : "Too few to judge"}
            {` across ${count(data.overall.n_measured)} measured alerts. `}
            {Array.isArray(data.tickers_measured) ? `${data.tickers_measured.length} tickers covered.` : "Ticker coverage unknown."}
          </p>}
          <p className="th-meta">Incomplete forward windows are excluded, not counted as losses. Missing comparisons stay unavailable. These historical figures do not change any trading rule.</p>
        </>}
        {model.status === "loading" && <p role="status">Loading the historical statistical estimate...</p>}
        {model.status === "unavailable" && <p role="status">{model.reason === "public-only" ? "Historical statistical estimate unavailable in Public-only mode. No legacy fit was started." : "Historical statistical estimate unavailable."}</p>}
        {model.status === "ready" && <p>
          {fitted.stage === 0 ? "Not calibrated" : `Historical fit reported at stage ${fitted.stage}${typeof fitted.model_kind === "string" ? ` (${fitted.model_kind})` : ""}`}
          {` - sample ${count(fitted.n)}. Fit time: ${dateText(fitted.trained_at)}. `}
          {typeof fitted.method_note === "string" ? fitted.method_note : ""}
          {" This is not a promised win rate or approval to trade."}
        </p>}
      </div>}
    </section>
  );
}
