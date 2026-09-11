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

  useEffect(() => {
    if (!ticker) {
      setBadges([]);
      return undefined;
    }
    let cancelled = false;
    const ctrl = new AbortController();
    setBadges([]);
    axios
      .get(
        `${BACKEND_API}/alerts/${encodeURIComponent(ticker)}`,
        { timeout: 15000, signal: ctrl.signal }
      )
      .then((r) => {
        if (cancelled) return;
        const alerts = r?.data?.alerts || [];
        setBadges(
          alerts
            .map((a) => alertEngineBadgeFor(a.type))
            .filter((b) => b != null)
        );
      })
      .catch(() => {
        if (!cancelled) setBadges([]);
      });
    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [ticker]);

  if (!badges.length) return null;

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
    </div>
  );
}
