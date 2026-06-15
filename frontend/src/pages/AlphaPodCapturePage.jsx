import React, { useState, useEffect, useRef, useCallback } from "react";

const APHUB = "http://localhost:3456";
const HEALTH_PATH = "/favicon.svg"; // any cheap static asset — liveness probe only

/**
 * AlphaPodCapturePage
 * Embeds a captured alphapod-hub page as a full-height iframe.
 * Requires the alphapod-hub server running at localhost:3456 (run `decoder`).
 *
 * Liveness note: the probe uses mode:"no-cors" on purpose. alphapod-hub's
 * server.py sets Access-Control-Allow-Origin only on its JSON/API responses,
 * NOT on static files (favicon.svg, captured/*.html). A normal cors-mode fetch
 * from the React origin (:3000) to :3456 would therefore be blocked by the
 * browser and throw — reporting a false "offline" even while the server is up.
 * A no-cors HEAD resolves (opaque) whenever the server is reachable and rejects
 * only on a genuine connection failure, which is exactly the signal we want.
 */
export default function AlphaPodCapturePage({ src, label }) {
  const [status, setStatus] = useState("loading"); // loading | ok | offline
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const runHealthCheck = useCallback(async () => {
    setStatus("loading");
    try {
      await fetch(`${APHUB}${HEALTH_PATH}`, {
        method: "HEAD",
        mode: "no-cors",
        cache: "no-store",
        signal: AbortSignal.timeout(2000),
      });
      if (mountedRef.current) setStatus("ok");
    } catch {
      if (mountedRef.current) setStatus("offline");
    }
  }, []);

  useEffect(() => { runHealthCheck(); }, [runHealthCheck]);

  const fullSrc = `${APHUB}${src}`;

  if (status === "offline") {
    return (
      <div style={{
        flex: 1, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center",
        background: "var(--bg)", color: "var(--text-secondary)",
        gap: 16, padding: 32,
      }}>
        <div style={{ fontSize: 32 }}>⚡</div>
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>
          AlphaPod Hub server is not running
        </div>
        <div style={{ fontSize: 12, color: "var(--text-tertiary)", textAlign: "center", maxWidth: 480 }}>
          Start it with one command, then refresh this page:
        </div>
        <pre style={{
          background: "var(--surface-1)", border: "1px solid var(--border-c)",
          borderRadius: 8, padding: "12px 20px", fontSize: 12,
          color: "var(--gold)", fontFamily: "monospace",
        }}>
          cd ~/Documents/GitHub/alphapod-hub && python3 server.py
        </pre>
        <div style={{ fontSize: 11, color: "var(--text-quaternary)" }}>
          Or run <code style={{ color: "var(--amber)" }}>decoder</code> — the updated launcher starts it automatically.
        </div>
        <button
          onClick={runHealthCheck}
          style={{
            marginTop: 8, padding: "8px 20px", borderRadius: 6,
            background: "var(--gold-dim)", border: "1px solid var(--gold-border)",
            color: "var(--gold)", fontSize: 12, cursor: "pointer",
          }}
        >
          Retry connection
        </button>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, position: "relative" }}>
      {status === "loading" && (
        <div style={{
          position: "absolute", inset: 0, display: "flex",
          alignItems: "center", justifyContent: "center",
          background: "var(--bg)", zIndex: 10,
          color: "var(--text-quaternary)", fontSize: 13,
        }}>
          Loading {label}…
        </div>
      )}
      <iframe
        src={fullSrc}
        title={label}
        onLoad={() => mountedRef.current && setStatus("ok")}
        style={{
          flex: 1, border: "none", width: "100%", height: "100%",
          minHeight: "calc(100vh - 48px)",
          opacity: status === "ok" ? 1 : 0,
          transition: "opacity 0.2s",
        }}
        allow="fullscreen"
        referrerPolicy="no-referrer"
      />
    </div>
  );
}
