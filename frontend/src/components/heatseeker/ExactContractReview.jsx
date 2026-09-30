import React, { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";

/** Read-only exact identity against the displayed recorded observation. No wall-midpoint guess. */
export default function ExactContractReview({ ticker, data, wall, cell = null, replay = false, testPrefix = "exact-contract" }) {
  const candidates = useMemo(() => {
    const list = [...(data?.scout?.shortlist?.CALLS || []), ...(data?.scout?.shortlist?.PUTS || [])];
    return list.filter(c => !wall || (typeof c.strike === "number" && c.strike >= wall.low && c.strike <= wall.high));
  }, [data, wall]);
  const [identity, setIdentity] = useState(null);
  const [strike, setStrike] = useState(cell?.strike == null ? "" : String(cell.strike));
  const [expiry, setExpiry] = useState(cell?.colKey || "");
  const [side, setSide] = useState("");
  const [result, setResult] = useState(null);
  const [loadingKey, setLoadingKey] = useState(null);
  const generation = useRef(0);
  const snapshot = data?.snapshotId || data?.snapshot_id || null;
  const scopeKey = `${ticker}|${wall?.wall_id || ""}|${snapshot || ""}|${replay}`;
  const requestKey = identity ? `${scopeKey}|${JSON.stringify(identity)}` : null;
  useEffect(() => {
    if (!identity || !snapshot) return undefined;
    const gen = ++generation.current;
    const ctrl = new AbortController();
    setLoadingKey(requestKey);
    setResult(null);
    axios.get(`${API}/solstice/${encodeURIComponent(ticker)}/contract`, {
      params: { ...identity, snapshot_id: snapshot }, timeout: 20000, signal: ctrl.signal,
    }).then(r => { if (gen === generation.current) setResult({ key: requestKey, body: r.data }); })
      .catch(e => { if (gen === generation.current && !ctrl.signal.aborted) setResult({ key: requestKey, error: e?.response?.data?.detail || "Exact contract review unavailable" }); })
      .finally(() => { if (gen === generation.current) setLoadingKey(null); });
    return () => { generation.current++; ctrl.abort(); };
  }, [requestKey, snapshot, ticker, identity]);
  const current = result?.key === requestKey ? result : null;
  const body = current?.body;
  const quote = body?.quote;
  const matched = body?.matched_identity;
  const choose = c => setIdentity(c.osi ? { osi: c.osi } : { strike: String(c.strike), expiry: c.expiry, type: c.type });
  return <section className="exact-contract-review" data-testid={testPrefix} aria-label="Exact listed contract review">
    <p>Choose a listed identity. A wall is a zone, not a contract. Read-only · {replay ? "recorded replay" : "displayed snapshot"}.</p>
    {!snapshot && <p role="status">No recorded snapshot identity — contract review unavailable.</p>}
    {candidates.length ? <table className="triad-contract-table"><thead><tr><th>Contract</th><th>Expiry</th><th>Δ</th><th>Bid / Ask</th><th>Spread</th><th>Review</th></tr></thead>
      <tbody>{candidates.map((c, i) => <tr key={c.osi || i} data-testid="triad-contract-row">
        <td>{c.osi || `${c.type} ${c.strike}`}</td><td>{c.expiry}</td><td>{c.delta ?? "—"}</td><td>{c.bid ?? "—"} / {c.ask ?? "—"}</td>
        <td>{typeof c.bid === "number" && typeof c.ask === "number" ? (c.ask - c.bid).toFixed(2) : "—"}</td>
        <td><button disabled={!snapshot} onClick={() => choose(c)} aria-label={`Review ${c.osi || `${c.type} ${c.strike} ${c.expiry}`}`}>Review</button></td>
      </tr>)}</tbody></table> : <p>No listed shortlist contract at this wall in this snapshot. Enter an explicit identity to resolve; no substitute is chosen.</p>}
    <form onSubmit={e => { e.preventDefault(); setIdentity({ strike, expiry, type: side }); }}>
      <label>Exact strike <input aria-label="Exact strike" value={strike} onChange={e => { setIdentity(null); setStrike(e.target.value); }} inputMode="decimal" /></label>
      <label>Listed expiry <select aria-label="Listed expiry" value={expiry} onChange={e => { setIdentity(null); setExpiry(e.target.value); }}>
        <option value="">Choose expiry</option>{(data?.grid?.expiries || []).map(d => <option key={d} value={d}>{d}</option>)}
      </select></label>
      <label>Option type <select aria-label="Option type" value={side} onChange={e => { setIdentity(null); setSide(e.target.value); }}>
        <option value="">Choose type</option><option value="call">Call</option><option value="put">Put</option>
      </select></label>
      <button disabled={!snapshot || !strike || !expiry || !side}>Resolve exact contract</button>
    </form>
    {loadingKey === requestKey && requestKey && <p role="status">Loading exact recorded contract…</p>}
    {current?.error && <p role="alert" data-testid={`${testPrefix}-error`}>{current.error}</p>}
    {body && body.status !== "ok" && <p role="status">Unavailable · {body.reason || "no exact match"}</p>}
    {body?.status === "ok" && <div data-testid={`${testPrefix}-result`}>
      <strong>{matched?.osi || `${matched?.type} ${matched?.strike} ${matched?.expiry}`}</strong>
      <dl><dt>Bid / Ask</dt><dd>{quote?.bid ?? "—"} / {quote?.ask ?? "—"}</dd>
        <dt>Spread</dt><dd>{quote?.spread_absolute ?? "—"}</dd>
        <dt>Quote ages · bid / ask</dt><dd>{quote?.ages_s?.bid ?? "unknown"} / {quote?.ages_s?.ask ?? "unknown"}</dd>
        <dt>Multiplier provenance</dt><dd>{body.multiplier?.value ?? "unknown"} · {body.multiplier?.source || "unknown"}</dd>
        <dt>Source</dt><dd>{quote?.quote_source || "unknown"} · snapshot {body.snapshot_id || "unknown"}</dd></dl>
    </div>}
  </section>;
}
