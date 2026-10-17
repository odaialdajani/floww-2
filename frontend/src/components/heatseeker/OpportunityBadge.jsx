/**
 * OpportunityBadge.jsx — STEAL-LIST #8
 *
 * Renders the opportunity engine readout for the canonical steal-list
 * rank #8 (regime classifier + opportunity scoring + risk-defined
 * trade-idea arbitration). Consumes
 *
 *   GET http://localhost:8000/api/opportunity/{ticker}
 *      → { regime, opportunity_score, opportunity_tier, direction,
 *          trade_type, trade_bias, invalidation, components, warnings }
 *
 * so the Solstice page shows a direct, readable readout of "what the
 * market regime is + what the engine is recommending + why you'd
 * invalidate it" — the precise surface the steal-list .md entry #8
 * promises ("Surface as a new Zenith 'Trade Ideas' card next to
 * Flowseeker").
 *
 * Visual treatment mirrors `HeatseekerDashboard.jsx`'s slate palette
 * (text-slate-200, bg-slate-900/40, traffic-light tier mapping).
 *
 * Defensive degrade: any backend failure (timeout / 500 / unreachable)
 * shows an amber offline card, not a crash. The engine itself degrades
 * to (regime=None, tier=LOW, trade_type=no_trade) when inputs are
 * missing — the badge renders that as a slate-LOW pill row with the
 * headline "Unknown Regime / no trade" so the dashboard never breaks
 * on a cold cache.
 */

import React, { memo, useEffect, useState } from "react";
import { BACKEND_BASE } from "../../config/api";
import { fetchStudyJSON } from "./studyFetch";
import StudyErrorCard from "./StudyErrorCard";

const SIDE_BASE =
  process.env.REACT_APP_STEAL_THREE_BASE || BACKEND_BASE;

// Tier colour map — HIGH=emerald (best), MED=sky, WATCH=amber, LOW=slate.
// Pulse-dot colour on the header tracks the same map so the lifecycle is
// visible at a glance.
const TIER_STYLES = {
  HIGH: {
    pill: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    text: "text-emerald-300",
    dot: "bg-emerald-400",
    bar: "bg-emerald-400/70",
  },
  MED: {
    pill: "bg-sky-500/15 text-sky-300 border-sky-500/30",
    text: "text-sky-300",
    dot: "bg-sky-400",
    bar: "bg-sky-400/70",
  },
  WATCH: {
    pill: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    text: "text-amber-300",
    dot: "bg-amber-400",
    bar: "bg-amber-400/70",
  },
  LOW: {
    pill: "bg-slate-500/15 text-slate-300 border-slate-500/30",
    text: "text-slate-300",
    dot: "bg-slate-400",
    bar: "bg-slate-400/60",
  },
};

// Trade-bias micro-pill palette. The user-visible semantics:
//   long_premium   → rose   (bullish / debit-style bias)
//   short_premium  → emerald (premium-selling bias — preferred edge)
//   defensive      → slate  (no clean direction / hedging only)
const BIAS_STYLES = {
  long_premium: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  short_premium: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  defensive: "bg-slate-500/15 text-slate-400 border-slate-500/30",
};

function fmt(n, d = 0) {
  return n == null ? "—" : Number(n).toFixed(d);
}

/** Safe token render — replaces engine-side underscores with spaces,
 *  falls back to a placeholder when the field is null, empty, or any
 *  case-variant of "none"/"null" (forward-compat against any future
 *  engine payload that falls back on a string sentinel instead of
 *  JSON null). */
function safeTok(s, fallback) {
  if (s == null || (typeof s === "string" && (/^\s*(none|null)\s*$/i.test(s) || s.trim() === ""))) {
    return fallback;
  }
  return String(s).replace(/_/g, " ");
}

function OpportunityBadge({ ticker = "SPY" }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setErr(null);
    fetchStudyJSON(`${SIDE_BASE}/api/opportunity/${encodeURIComponent(ticker)}`)
      .then((j) => {
        if (!cancelled) setData(j);
      })
      .catch((e) => {
        if (!cancelled) setErr(e);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (err) {
    return (
      <StudyErrorCard
        title="Opportunity"
        base={SIDE_BASE}
        error={err}
        testId="hs-opportunity"
        className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3"
      />
    );
  }

  if (!data) {
    return (
      <div
        className="rounded-xl border border-slate-700/30 bg-slate-900/40 animate-pulse p-3"
        data-testid="hs-opportunity"
      >
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-1">
          Opportunity · {ticker}
        </div>
        <div className="text-[10px] text-slate-400">scoring…</div>
      </div>
    );
  }

  const tier = data.opportunity_tier || "LOW";
  const tierStyle = TIER_STYLES[tier] || TIER_STYLES.LOW;
  const biasStyle =
    BIAS_STYLES[data.trade_bias] || BIAS_STYLES.defensive;

  const score = Number.isFinite(Number(data.opportunity_score))
    ? Number(data.opportunity_score)
    : 0;
  // Clamp to [0, 10] before computing pct — protects against malformed
  // future payloads where the engine might relax the [0,10] clamp.
  const scoreClamped = Math.max(0, Math.min(10, score));
  const scorePct = (scoreClamped / 10) * 100;

  return (
    <div
      className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3"
      data-testid="hs-opportunity"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className={`w-1.5 h-1.5 rounded-full animate-pulse ${tierStyle.dot}`}
          />
          <span className="text-[10px] uppercase tracking-widest font-bold text-slate-200">
            Opportunity Engine · {ticker}
          </span>
        </div>
        <span
          className={`text-[9px] uppercase tracking-widest font-mono ${tierStyle.text}`}
        >
          {tier} · {fmt(score, 1)}/10
        </span>
      </div>

      {/* Opportunity_score gauge */}
      <div className="h-1.5 rounded bg-slate-800/60 overflow-hidden mb-3">
        <div
          className={`h-full ${tierStyle.bar}`}
          style={{ width: `${scorePct}%` }}
        />
      </div>

      {/* Regime (big) + trade_type (medium) pills */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span
          className={`px-3 py-1.5 rounded-lg border text-xs font-bold ${tierStyle.pill}`}
        >
          {safeTok(data.regime, "Unknown Regime")}
        </span>
        <span
          className={`px-2 py-1 rounded border text-[10px] font-mono uppercase tracking-wider ${tierStyle.pill}`}
        >
          {safeTok(data.trade_type, "no trade")}
        </span>
      </div>

      {/* Trade-bias micro-pill */}
      <div className="mb-2">
        <span
          className={`inline-block text-[9px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded border ${biasStyle}`}
        >
          bias: {safeTok(data.trade_bias, "defensive")}
        </span>
      </div>

      {/* Invalidation rule */}
      <div className="text-[9px] text-slate-500 border-t border-slate-800/40 pt-2 mt-1 leading-snug">
        {data.invalidation || "—"}
      </div>
    </div>
  );
}

export default memo(OpportunityBadge);
