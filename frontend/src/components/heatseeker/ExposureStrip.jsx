import React, { useEffect, useState } from "react";
import axios from "axios";
import { API as BACKEND_API } from "../../config/api";
import { exposureBadgeFor } from "../flowseeker/exposureBadges";
import "./ExposureStrip.css";

/**
 * ExposureStrip — per-ticker backend exposure-rule badges for heatseeker.
 *
 * Reads the persisted v3 feed (/api/flowseeker/alerts/feed?ticker=X), which
 * already carries exposure rows (rule TOXIC_FLOW / GAMMA_FLIP / VEX_WALL /
 * CHARM_PIN / LIQUIDITY_STRESS) written by the heatmap route + snapshot
 * path. Renders one badge per live rule; unknown rules never render.
 * Fail-open: empty feed or fetch failure renders nothing, never blanks.
 */
export default function ExposureStrip({ ticker }) {
  const [badges, setBadges] = useState([]);

  useEffect(() => {
    if (!ticker) return undefined;
    let cancelled = false;
    const ctrl = new AbortController();
    setBadges([]); // drop the previous ticker's badges immediately; the
    // fetch below either replaces them or leaves the strip empty
    axios
      .get(
        `${BACKEND_API}/flowseeker/alerts/feed?ticker=${encodeURIComponent(ticker)}&days=2`,
        { timeout: 15000, signal: ctrl.signal }
      )
      .then((r) => {
        if (cancelled) return;
        const rows = r?.data?.alerts || [];
        const seen = new Map();
        for (const row of rows) {
          const b = exposureBadgeFor(row?.rule);
          if (b && !seen.has(b.rule)) seen.set(b.rule, b);
        }
        setBadges([...seen.values()]);
      })
      .catch(() => {
        // fail-open AND stale-free: a failed fetch must not leave the
        // previous ticker's badges on screen under the new ticker
        if (!cancelled) setBadges([]);
      });
    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [ticker]);

  if (!badges.length) return null;

  return (
    <div className="skylit-exp-strip" data-testid="skylit-exp-strip">
      {badges.map((b) => (
        <span
          key={b.rule}
          className={`skylit-exp-badge e-${b.rule.toLowerCase()}`}
          title={b.title}
        >
          {b.label}
        </span>
      ))}
    </div>
  );
}
