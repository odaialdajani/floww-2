import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";

const count=value=>typeof value==="number" && Number.isFinite(value) && value>=0 && Number.isInteger(value)?value.toLocaleString():"Unknown";
export default function MarketCoverage({ coverage }) {
  const [release, setRelease] = useState(null);
  // "pending" | "ok" | "failed" are genuinely different facts. Collapsing
  // them into one "not available yet" string made a permanent failure
  // indistinguishable from a first load, so an operator could believe the
  // release state was merely stale when nothing was being checked at all.
  const [releaseState, setReleaseState] = useState("pending");
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => axios.get(`${API}/market/provider-updates`, { signal: controller.signal, timeout: 30000 })
      .then(({ data }) => { setRelease(data); setReleaseState("ok"); })
      .catch((e) => {
        if (controller.signal.aborted) return;
        setRelease(null);
        setReleaseState("failed");
      });
    refresh();
    const id = setInterval(refresh, 300000);
    return () => { clearInterval(id); controller.abort(); };
  }, []);
  const checkedAt = Date.parse(release?.checked_at);
  const checkIsRecent = Number.isFinite(checkedAt) && Date.now() - checkedAt >= -60000 && Date.now() - checkedAt < 26 * 3600000;
  return <div className="th-coverage" aria-label="Automatic scan coverage" style={{ padding: "8px 12px", fontSize: 12, color: "#b6bfd0", lineHeight: 1.5 }}>
    {coverage ? <>
      <strong>{count(coverage.universe)} stocks and funds in the automatic scan{coverage.scope_kind === "provider_option_enabled" ? " · listed options only" : ""}</strong>
      {" · "}{count(coverage.fresh)} checked within {Math.max(1, Math.round((coverage.fresh_window_seconds || 60) / 60))} minute(s) at the last scan
      {" · "}{count(coverage.never_scanned)} still waiting
      {" · "}{count(coverage.latest_failed)} without usable fresh data.
      {coverage.source === "custom-universe" && " A custom stock list limits this scan."}
      {coverage.catalog_available === false && " The provider's full list is unavailable."}
      {coverage.catalog_stale && " Using the last saved stock list."}
      {coverage.progress?.status === "durable" && <p className="th-coverage-progress">Scan position is saved · {count(coverage.progress.pending)} names remain in this pass{coverage.progress.deferred > 0 ? ` · of which ${count(coverage.progress.deferred)} are waiting for the call allowance` : ""}.</p>}
      {coverage.progress?.status === "unavailable" && <p className="th-coverage-progress" role="status">Scan progress could not be saved. New checks are paused.</p>}
      {coverage.progress?.status === "awaiting_directory" && <p className="th-coverage-progress" role="status">The saved scan position is kept. Waiting for the provider stock list.</p>}
      <details className="th-coverage-details"><summary>Scan coverage and limits</summary>
      {typeof coverage.provider_listed_tickers === "number" && <p>{count(coverage.provider_listed_tickers)} names in the provider list · {count(coverage.eligible_option_tickers)} have options enabled for this scan. Other names may not offer option chains.</p>}
      Checks up to {coverage.expiries_per_ticker || 2} upcoming expiries per stock.
      {" "}Results show unusual activity from available snapshots; this is not a live feed of every trade.
      {coverage.estimated_pass_seconds > 0 && ` A full pass at the last scan's pace takes about ${Math.ceil(coverage.estimated_pass_seconds / 60)} minutes of scanning.`}
      {coverage.rows_capped && " Some stocks reached the per-stock results limit."}
      {coverage.conflicting_contracts_excluded > 0 && ` ${Number(coverage.conflicting_contracts_excluded).toLocaleString()} conflicting contract readings were excluded.`}
      {coverage.history_contract_limit > 0 && <>
        {" "}Keeps earlier readings for up to {coverage.history_contract_limit} contracts per stock.
        {" "}Changes between snapshots do not prove when trades happened.
        {coverage.history_unavailable > 0 && ` Saved comparisons are unavailable for ${Number(coverage.history_unavailable).toLocaleString()} stocks.`}
        {coverage.history_capped > 0 && ` ${Number(coverage.history_capped).toLocaleString()} stocks reached the saved-comparison limit.`}
      </>}
      </details>
    </> : "Automatic scan coverage is not available yet."}
    <br />
    {releaseState === "failed" ? (
      <span data-testid="release-check-failed">
        Provider release check could not be completed — the provider status endpoint is unreachable. New provider functions stay unusable until this succeeds.
      </span>
    ) : releaseState === "pending" ? (
      <span data-testid="release-check-pending">Provider release check pending…</span>
    ) : release?.status === "current" && checkIsRecent
      ? "Provider release check: no changes since the last review."
      : release?.status === "review_needed"
        ? "Provider changes found: review needed before new functions can be used."
        : (
          <span data-testid="release-check-unknown">
            Provider release check returned an unrecognised status
            {release?.status ? ` (${release.status})` : ""}; treat the release state as unverified.
          </span>
        )}
    {Number.isFinite(checkedAt) && ` Last checked ${new Date(checkedAt).toLocaleString()}.`}
  </div>;
}
