import React, { useEffect, useState } from "react";
import axios from "axios";
import { API } from "../../config/api";

export default function MarketCoverage({ coverage }) {
  const [release, setRelease] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => axios.get(`${API}/market/provider-updates`, { signal: controller.signal, timeout: 30000 })
      .then(({ data }) => setRelease(data)).catch(() => {});
    refresh();
    const id = setInterval(refresh, 300000);
    return () => { clearInterval(id); controller.abort(); };
  }, []);
  const checkedAt = Date.parse(release?.checked_at);
  const checkIsRecent = Number.isFinite(checkedAt) && Date.now() - checkedAt >= -60000 && Date.now() - checkedAt < 26 * 3600000;
  return <div aria-label="Automatic scan coverage" style={{ padding: "8px 12px", fontSize: 12, color: "#b6bfd0", lineHeight: 1.5 }}>
    {coverage ? <>
      <strong>{Number(coverage.universe || 0).toLocaleString()} stocks and funds in the automatic scan</strong>
      {" · "}{Number(coverage.fresh || 0).toLocaleString()} checked within {Math.max(1, Math.round((coverage.fresh_window_seconds || 60) / 60))} minute(s) at the last scan
      {" · "}{Number(coverage.never_scanned || 0).toLocaleString()} still waiting
      {" · "}{Number(coverage.latest_failed || 0).toLocaleString()} without usable fresh data.
      {coverage.source === "custom-universe" && " A custom stock list limits this scan."}
      {coverage.catalog_available === false && " The provider's full list is unavailable."}
      {coverage.catalog_stale && " Using the last saved stock list."}
      <br />
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
    </> : "Automatic scan coverage is not available yet."}
    <br />
    {release?.status === "current" && checkIsRecent ? "Provider release check: no changes since the last review."
      : release?.status === "review_needed" ? "Provider changes found: review needed before new functions can be used."
        : "Provider release check is not available yet."}
    {Number.isFinite(checkedAt) && ` Last checked ${new Date(checkedAt).toLocaleString()}.`}
  </div>;
}
