/**
 * AlertEngineStrip — per-ticker alert-engine badge strip (heatseeker panel).
 *
 * Reads the live alert-engine detector response (/api/alerts/{ticker}),
 * maps each Alert.type through alertEngineBadgeFor(), and renders one badge
 * per live alert-engine rule. GAMMA_FLIP is excluded here (handled by
 * exposureBadges + ExposureStrip) — the same string is fired by two producers
 * and cannot be split on the string alone.
 *
 * Contract-shaped synthetic fixtures only — no live feed required.
 * Fail-open: empty response or fetch failure renders nothing.
 */

import React, { useEffect, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../../config/api";
import { alertEngineBadgeFor } from "../flowseeker/alertEngineBadges";
import "./AlertEngineStrip.css";

export default function AlertEngineStrip({ ticker }) {
  const [badges, setBadges] = useState([]);
  const [withheldStale, setWithheldStale] = useState(0);

  useEffect(() => {
    if (!ticker) {
      setBadges([]);
      setWithheldStale(0);
      return undefined;
    }
    let cancelled = false;
    const ctrl = new AbortController();
    setBadges([]);
    setWithheldStale(0);
    axios
      .get(
        `${BACKEND_API}/alerts/${encodeURIComponent(ticker)}`,
        { timeout: 15000, signal: ctrl.signal }
      )
      .then((r) => {
        if (cancelled) return;
        const alerts = r?.data?.alerts || [];
        // R8-04: suppress stale evidence. Alerts older than the engine's
        // own 24h summary window are withheld (counted, never silently
        // dropped without a trace); missing/unparseable timestamps stay
        // visible (backend always stamps ISO — fail open on shape drift).
        const now = Date.now();
        let stale = 0;
        const fresh = [];
        for (const a of alerts) {
          let age = null;
          try {
            const t = Date.parse(a?.timestamp);
            if (Number.isFinite(t)) age = now - t;
          } catch { /* keep null → visible */ }
          if (age !== null && age > 24 * 3600 * 1000) {
            stale += 1;
            continue;
          }
          fresh.push(a);
        }
        setWithheldStale(stale);
        setBadges(
          fresh
            .map((a) => alertEngineBadgeFor(a.type))
            .filter((b) => b != null)
        );
      })
      .catch(() => {
        if (!cancelled) { setBadges([]); setWithheldStale(0); }
      });
    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [ticker]);

  if (!badges.length && !withheldStale) return null;

  return (
    <div className="skylit-alert-engine-strip" data-testid="skylit-alert-engine-strip">
      {badges.map((b) => (
        <span
          key={b.rule}
          className={`skylit-ae-badge ae-${b.rule.toLowerCase()}`}
          title={b.title}
          aria-label={b.title}
        >
          {b.label}
        </span>
      ))}
      {withheldStale > 0 && (
        <span className="skylit-ae-badge ae-stale"
          data-testid="skylit-ae-stale"
          title={`${withheldStale} alert(s) older than 24h withheld as stale evidence`}>
          +{withheldStale} stale withheld
        </span>
      )}
    </div>
  );
}
