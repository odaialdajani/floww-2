import React, { useCallback, useEffect, useRef, useState } from "react";
import { API } from "../../config/api";
import { storedAppKeyHeaders } from "../../utils/appKey";

const count = value => Number.isInteger(value) && value >= 0;
const text = value => typeof value === "string" && value.trim().length > 0;
const optionalText = value => value == null || typeof value === "string";
function refusal(data) {
  if (data?.version !== "lifecycle-inventory.v1") return "INVENTORY_VERSION_UNSUPPORTED";
  const intents = data.intents;
  if (typeof data.durable !== "boolean" || typeof data.storeless !== "boolean" || data.durable === data.storeless
    || typeof data.live_submission_armed !== "boolean"
    || !intents || !count(intents.n_known) || !Array.isArray(intents.open) || !Array.isArray(intents.unknown)
    || intents.n_open !== intents.open.length || intents.n_unknown !== intents.unknown.length
    || intents.n_known < intents.n_open + intents.n_unknown
    || [...intents.open, ...intents.unknown].some(row => !text(row?.intent_id) || !text(row.state)
          || !optionalText(row.order_id) || !optionalText(row.ticker) || !optionalText(row.owner)
          || typeof row.has_approval !== "boolean" || typeof row.protection?.protected !== "boolean" || !optionalText(row.protection.reason))
    || intents.unknown.some(row => row.state !== "UNKNOWN") || intents.open.some(row => row.state === "UNKNOWN")
    || !count(data.drafts?.n_staged) || !Array.isArray(data.native_workflows)
    || data.native_workflows.some(row => !text(row?.strategy) || !text(row.venue) || !text(row.status))
    || !count(data.preflight?.n_cached_contexts) || !data.recovery
    || (data.recovery.durable_nonterminal_rows !== null && !count(data.recovery.durable_nonterminal_rows))
    || typeof data.protection?.entry_pause_now !== "boolean" || typeof data.protection?.cancel_allowed_during_pause !== "boolean"
    || data.policy?.account_wide_limits !== "UNSET") return "INVENTORY_SHAPE_UNAVAILABLE";
  return null;
}

/** A local registry read is never account-wide ownership or permission to trade. */
export default function PublicLifecycleInventory({ accountId, connected = false }) {
  const [result, setResult] = useState(null), [loading, setLoading] = useState(false);
  const epoch = useRef(0), controller = useRef(null);
  const clear = useCallback(() => {
    epoch.current++;
    controller.current?.abort();
    setResult(null); setLoading(false);
  }, []);
  useEffect(() => {
    clear();
    const storage = event => { if (event.key === "floww_app_key" || event.key === "floww-research-session-ended" || event.key === null) clear(); };
    window.addEventListener("storage", storage);
    window.addEventListener("floww-research-session-ended", clear);
    return () => {
      epoch.current++; controller.current?.abort();
      window.removeEventListener("storage", storage);
      window.removeEventListener("floww-research-session-ended", clear);
    };
  }, [accountId, connected, clear]);
  const read = useCallback(async () => {
    if (!connected) return;
    clear();
    const headers = storedAppKeyHeaders();
    if (!headers) { setResult({ reason: "APP_KEY_MISSING" }); return; }
    const id = ++epoch.current, ctrl = new AbortController(); controller.current = ctrl;
    const timer = setTimeout(() => ctrl.abort(), 15000);
    setLoading(true);
    try {
      const response = await fetch(`${API}/public/execution-lifecycle/inventory`, { headers, signal: ctrl.signal });
      if (response.status === 401 || response.status === 503) throw new Error("APP_KEY_REJECTED");
      if (!response.ok) throw new Error(`INVENTORY_HTTP_${response.status}`);
      const data = await response.json();
      if (epoch.current !== id || ctrl.signal.aborted) return;
      if (storedAppKeyHeaders()?.["X-API-Key"] !== headers["X-API-Key"]) { clear(); return; }
      const reason = refusal(data);
      setResult(reason ? { reason } : { data, receivedAt: new Date().toISOString() });
    } catch (error) {
      if (epoch.current === id) setResult({ reason: ctrl.signal.aborted ? "INVENTORY_READ_TIMEOUT" : error.message || "INVENTORY_READ_FAILED" });
    } finally {
      clearTimeout(timer);
      if (epoch.current === id) setLoading(false);
    }
  }, [connected, clear]);
  const data = result?.data;
  return <section aria-label="Local lifecycle review" className="space-y-2 text-sm">
    <details>
      <summary>Local lifecycle inventory · read-only</summary>
      <p>Account attribution unavailable: this registry is not bound to the displayed Public account. Local counts do not establish broker positions, open orders or native ownership. Entry remains unavailable.</p>
      <button type="button" className="btn" onClick={read} disabled={!connected || loading}
        title={!connected ? "Current account connection is unavailable" : loading ? "Waiting for the local registry read" : "Authenticated GET only; no approval, recovery or broker call"}>Read local lifecycle inventory</button>
      {!connected && <p role="status">Current account connection unavailable; review read disabled.</p>}
      {loading && <p role="status">Reading local registry…</p>}
      {result?.reason && <p role="status">Local inventory unavailable · {result.reason}</p>}
      {data && <>
        <p>Received {result.receivedAt} · not a producer or broker clock.</p>
        <p>{data.storeless ? "Storeless; open broker inventory unknown" : "Store registered; restart survival unverified"}. {data.recovery.durable_nonterminal_rows === null ? "Stored nonterminal count unavailable" : `${data.recovery.durable_nonterminal_rows} stored nonterminal rows; count only, not rehydrated or reconciled here`}.</p>
        <p>{data.intents.n_known} process-local known records · {data.intents.n_open} local open · {data.intents.n_unknown} local unknown. Filled records are not a positions census.</p>
        {[...data.intents.open, ...data.intents.unknown].length > 0 && <div style={{ overflowX: "auto" }}><table aria-label="Process-local intent records" className="w-full text-xs" style={{ minWidth: 680 }}>
          <thead><tr><th>Intent / order</th><th>Symbol / owner</th><th>Local state</th><th>Approval field</th><th>Protection report</th></tr></thead>
          <tbody>{[...data.intents.open, ...data.intents.unknown].map(row => <tr key={row.intent_id}>
            <td>{row.intent_id} / {row.order_id || "Order identity unavailable"}</td><td>{row.ticker || "Unknown"} / {row.owner || "Unknown"}</td><td>{row.state}</td>
            <td>{row.has_approval ? "Local approval field present; authentication unverified" : "No local approval field"}</td>
            <td>{row.protection.protected ? "Protection reported; broker verification unavailable" : row.protection.reason || "Protection unverified"}</td>
          </tr>)}</tbody>
        </table></div>}
        <p>{data.drafts.n_staged} local draft rows · {data.preflight.n_cached_contexts} cached contexts; neither count establishes fresh preflight or permission.</p>
        <p>{data.native_workflows.length} local native registrations; not verified remote workflows. Workflows created outside FLOWW may still trade.</p>
        {data.native_workflows.length > 0 && <ul>{data.native_workflows.map((row, index) => <li key={index}>{row.strategy} · {row.venue} · reported {row.status}</li>)}</ul>}
        <p>Account-wide limits UNSET. Server submission flag {data.live_submission_armed ? "ON" : "OFF"}; this review cannot submit or change it.</p>
        <p>Weekday new-entry pause report: {data.protection.entry_pause_now ? "in window" : "outside window"} · 11:30–14:00 America/New_York. This is not exchange-calendar enforcement; holidays, early closes and expiry safeguards remain unverified. Cancellation allowed during pause: {data.protection.cancel_allowed_during_pause ? "reported yes" : "reported no"}; no cancellation, protection or recovery is executed here.</p>
      </>}
    </details>
  </section>;
}
