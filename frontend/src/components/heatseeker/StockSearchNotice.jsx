import React from "react";

export default function StockSearchNotice({ status, onRetry }) {
  if (status === "complete") return null;
  return <div role="status" style={{ padding: "8px 16px", color: "var(--text-secondary, #b6bfd0)", fontSize: 13 }}>
    {status === "loading" ? "Loading full stock search..."
      : status === "saved" ? "Stock search uses a saved provider list; its latest changes are unavailable."
        : "Stock search is incomplete. Some names may be missing from search and ticker buttons."}
    {status !== "loading" && <button type="button" onClick={onRetry}
      style={{ marginLeft: 12, textDecoration: "underline" }}>Retry stock list</button>}
  </div>;
}
