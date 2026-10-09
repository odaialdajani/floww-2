import React, { useState } from "react";
import { fmt, fmtAbs } from "../lib/helpers";
import { BACKEND_URL, API } from "../config/api";

// ============ Shared Null-Safety Helpers (no new imports) ============
const dash = (v, fn) => (v == null ? "—" : (fn ? fn(v) : v));
const safeFixed = (v, d) => (v != null && !isNaN(v)) ? v.toFixed(d) : "—";
const safePct = (v) => (v != null && !isNaN(v)) ? (v * 100).toFixed(1) + "%" : "—";

// ============ Loading / Error / Empty State Components ============
function LoadingState() {
  return <div className="panel p-3 text-slate-500">Loading…</div>;
}

function ErrorState({ error }) {
  return <div className="panel p-3 text-rose-400">{String(error)}</div>;
}

function EmptyState() {
  return <div className="panel p-3 text-slate-500">—</div>;
}

// ============ Collapsible Section Wrapper ============
function Section({ title, children, defaultOpen = true, badge }) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3">
      <button className="flex items-center justify-between w-full text-left" onClick={() => setOpen(!open)} style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}>
        <div className="flex items-center gap-2">
          <div className="text-xs font-semibold text-slate-200 uppercase tracking-wider">{title}</div>
          {badge && <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-slate-700/50 text-slate-400 font-medium">{badge}</span>}
        </div>
        <span className="text-slate-500 text-xs">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

// ============ Flip Zones Panel ============
export function FlipZonesPanel({ data, loading, error }) {
  if (error) return <ErrorState error={error} />;
  if (loading) return <LoadingState />;
  if (!data?.nodes) return <EmptyState />;
  const { spot, nodes } = data;
  return (
    <Section title="Flip Zones">
      <div className="flex gap-2 text-[10px] flex-wrap">
        {nodes.polarity_level != null && <FlipBadge label="GEX Flip" value={nodes.polarity_level} spot={spot} color="amber" />}
        {nodes.vex_flip != null && <FlipBadge label="VEX Flip" value={nodes.vex_flip} spot={spot} color="pink" />}
        {nodes.charm_flip != null && <FlipBadge label="Charm Flip" value={nodes.charm_flip} spot={spot} color="cyan" />}
        {nodes.max_pain != null && <FlipBadge label="Max Pain" value={nodes.max_pain} spot={spot} color="orange" />}
      </div>
    </Section>
  );
}

function FlipBadge({ label, value, spot, color }) {
  const pct = (spot != null && spot !== 0) ? safeFixed((value - spot) / spot * 100, 2) : "—";
  const dotColor = color === "amber" ? "bg-amber-400/60" : color === "pink" ? "bg-pink-500/60" : color === "cyan" ? "bg-cyan-400/60" : "bg-orange-400/60";
  const textColor = color === "amber" ? "text-amber-300" : color === "pink" ? "text-pink-300" : color === "cyan" ? "text-cyan-300" : "text-orange-300";
  return (
    <div className="flex items-center gap-1">
      <span className={`w-2 h-2 rounded-full ${dotColor}`} />
      <span className="text-slate-500">{label}:</span>
      <span className={`${textColor} font-bold mono`}>{fmt(value, 1)}</span>
      <span className="text-slate-600">({pct}%)</span>
    </div>
  );
}

// ============ Stacked Nodes Panel ============
export function StackedNodesPanel({ data, loading, error }) {
  if (error) return <ErrorState error={error} />;
  if (loading) return <LoadingState />;
  if (!data?.nodes?.stacked_nodes?.length) return <EmptyState />;
  return (
    <Section title="Stacked Nodes" badge={`${data.nodes.stacked_nodes.length}`}>
      <div className="space-y-0.5">
        {data.nodes.stacked_nodes.slice(0, 4).map((s, i) => (
          <div key={i} className="flex items-center gap-1.5 text-[9px]">
            <span className="mono text-slate-300 w-12">{fmt(s.strike, 0)}</span>
            <div className="flex-1 flex gap-0.5 items-center h-2">
              <div className="h-full rounded-l bg-teal-500/70" style={{ width: `${(s.call_pct ?? 0) * 100}%` }} />
              <div className="h-full rounded-r bg-purple-500/70" style={{ width: `${(s.put_pct ?? 0) * 100}%` }} />
            </div>
            <span className="text-teal-400 w-6 text-right">{Math.round((s.call_pct ?? 0) * 100)}</span>
            <span className="text-purple-400 w-6 text-right">{Math.round((s.put_pct ?? 0) * 100)}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ============ Tug of War Panel ============
export function TugOfWarPanel({ data, loading, error }) {
  if (error) return <ErrorState error={error} />;
  if (loading) return <LoadingState />;
  if (!data?.nodes?.tug_of_war?.length) return <EmptyState />;
  return (
    <Section title="Tug-of-War" badge={`${data.nodes.tug_of_war.length}`}>
      <div className="space-y-0.5">
        {data.nodes.tug_of_war.slice(0, 3).map((z, i) => (
          <div key={i} className="flex items-center gap-1.5 text-[9px]">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60" />
            <span className="mono text-slate-300">{fmt(z.low, 0)}–{fmt(z.high, 0)}</span>
            <span className="text-emerald-400">+{fmtAbs(z.positive)}</span>
            <span className="text-rose-400">{fmtAbs(z.negative)}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ============ Scenario Panel ============
export function ScenarioPanel({ data, loading, error }) {
  if (error) return <ErrorState error={error} />;
  if (loading) return <LoadingState />;
  if (!data?.nodes) return <EmptyState />;
  const { nodes, spot } = data;
  const kingStrike = nodes.king?.strike;
  return (
    <Section title="Scenario">
      <div className="space-y-1">
        {nodes.regime === "positive" && <>
          <div className="text-[9px] text-sky-400 font-bold">◎ RANGE DAY</div>
          <div className="text-[8px] text-slate-400">Positive-gamma backdrop for mean-reversion; needs observed holding at the wall.</div>
          {kingStrike != null && kingStrike > spot && <div className="text-[8px] text-rose-400">▽ Ceiling at {fmt(kingStrike, 0)}</div>}
          {kingStrike != null && kingStrike < spot && <div className="text-[8px] text-emerald-400">△ Floor at {fmt(kingStrike, 0)}</div>}
        </>}
        {nodes.regime === "negative" && <>
          <div className="text-[9px] text-amber-400 font-bold">⚡ TREND DAY</div>
          <div className="text-[8px] text-slate-400">Negative-gamma backdrop for momentum; needs observed continuation through the wall.</div>
        </>}
        {nodes.regime === "neutral" && <>
          <div className="text-[9px] text-orange-400 font-bold">⚠ WHIPSAW</div>
          <div className="text-[8px] text-slate-400">Mixed signals. Reduce size.</div>
        </>}
        {nodes.polarity_level != null && <div className="text-[8px] text-yellow-300">⟷ Flip at {fmt(nodes.polarity_level, 1)}</div>}
        {nodes.total_vega != null && Math.abs(nodes.total_vega) > 1e6 && <div className="text-[8px] text-slate-500">Vega: {fmtAbs(nodes.total_vega)}</div>}
        {nodes.put_call_ratio != null && <div className="text-[8px] text-slate-500">P/C Ratio: <span className={nodes.put_call_ratio > 1 ? "text-rose-400" : "text-emerald-400"}>{safeFixed(nodes.put_call_ratio, 2)}</span></div>}
      </div>
    </Section>
  );
}

// ============ Risk Dashboard Panel ============
export function RiskDashboardPanel({ data, loading, error }) {
  if (error) return <ErrorState error={error} />;
  if (loading) return <LoadingState />;
  if (!data?.nodes?.risk_metrics) return <EmptyState />;
  const rm = data.nodes.risk_metrics;
  return (
    <Section title="Risk Dashboard">
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[9px]">
        <RiskMetric label="GCI" value={safeFixed(rm.gci, 3)} warn={rm.gci > 0.25} caution={rm.gci > 0.15} />
        <RiskMetric label="PGR" value={safePct(rm.pgr)} warn={rm.pgr < 0.3} caution={rm.pgr < 0.5} invert />
        <RiskMetric label="GDW" value={fmtAbs(rm.gdw)} />
        <RiskMetric label="T-Amp" value={rm.time_amp != null ? rm.time_amp + "x" : "—"} />
        <RiskMetric label="CAR Net" value={safeFixed(rm.car_net, 1) + "M"} warn={rm.car_net < 0} invert />
        <RiskMetric label="CAR Gross" value={safeFixed(rm.car_gross, 1) + "M"} caution />
        <RiskMetric label="Charm Risk" value={safeFixed(rm.charm_risk, 1) + "M"} warn={Math.abs(rm.charm_risk || 0) > 50} />
        <RiskMetric label="Vomma" value={fmtAbs(data?.nodes?.total_vomma)} />
      </div>
      <div className="mt-1.5 text-[8px] text-slate-600 leading-tight">GCI: gamma concentration. PGR: protective gamma near spot. CAR: convexity acceleration risk.</div>
    </Section>
  );
}

function RiskMetric({ label, value, warn, caution, invert }) {
  const color = invert ? (warn ? "text-emerald-400" : caution ? "text-amber-400" : "text-rose-400") : (warn ? "text-rose-400" : caution ? "text-amber-400" : "text-slate-300");
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={`mono font-bold ${color}`}>{value}</span>
    </div>
  );
}

// ============ Opportunities Panel ============
export function OpportunitiesPanel({ data, loading, error }) {
  if (error) return <ErrorState error={error} />;
  if (loading) return <LoadingState />;
  if (!data?.opportunities?.length) return <EmptyState />;
  return (
    <Section title="Opportunities" badge={`${data.opportunities.length}`}>
      <div className="space-y-1.5">
        {data.opportunities.slice(0, 5).map((o, i) => (
          <div key={i} className={`text-[9px] p-1.5 rounded border-l-2 ${o.direction === "bullish" ? "border-emerald-500 bg-emerald-500/5" : o.direction === "bearish" ? "border-rose-500 bg-rose-500/5" : "border-amber-500 bg-amber-500/5"}`}>
            <div className="flex justify-between items-center">
              <span className="font-bold text-slate-200">{o.name}</span>
              <span className={`mono text-[8px] px-1 py-px rounded ${o.risk === "high" ? "bg-rose-500/20 text-rose-400" : o.risk === "medium" ? "bg-amber-500/20 text-amber-400" : "bg-emerald-500/20 text-emerald-400"}`}>{o.risk}</span>
            </div>
            <div className="text-slate-400 mt-0.5">{o.description}</div>
            <div className="flex gap-2 mt-0.5 text-[8px]">
              <span className="text-slate-500">conf: <span className="text-slate-300 mono">{safeFixed((o.confidence ?? 0) * 100, 0)}%</span></span>
              {o.entry?.length >= 2 && <span className="text-slate-500">entry: <span className="text-slate-300 mono">${o.entry[0]}–${o.entry[1]}</span></span>}
              {o.target != null && <span className="text-slate-500">target: <span className="text-emerald-400 mono">${fmt(o.target, 0)}</span></span>}
              {o.stop != null && <span className="text-slate-500">stop: <span className="text-rose-400 mono">${fmt(o.stop, 0)}</span></span>}
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ============ Implied Move Panel ============
export function ImpliedMovePanel({ data, loading, error }) {
  if (error) return <ErrorState error={error} />;
  if (loading) return <LoadingState />;
  if (!data?.implied_move) return <EmptyState />;
  const im = data.implied_move;
  const impliedPct = dash(im.implied_move_pct);
  const avgIvPct = safeFixed((im.avg_iv ?? 0) * 100, 1);
  return (
    <Section title="Implied Move">
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
        <div className="flex justify-between"><span className="text-slate-500">Expected</span><span className="mono text-amber-300 font-bold">±{impliedPct}%</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Range</span><span className="mono text-slate-300">${fmt(im.lower_range, 1)}–${fmt(im.upper_range, 1)}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">ATM Strike</span><span className="mono text-slate-300">{fmt(im.atm_strike, 0)}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Avg IV</span><span className="mono text-slate-300">{avgIvPct}%</span></div>
      </div>
      <div className="mt-1.5 h-2 bg-slate-800 rounded-full overflow-hidden relative">
        <div className="absolute inset-y-0 left-1/2 w-0.5 bg-slate-500" />
        <div className="absolute inset-y-0 bg-amber-500/30 rounded-full" style={{ left: `${Math.max(0, 50 - (im.implied_move_pct ?? 0) * 5)}%`, right: `${Math.max(0, 50 - (im.implied_move_pct ?? 0) * 5)}%` }} />
      </div>
      <div className="text-[8px] text-slate-600 mt-1">Market expects ±{impliedPct}% move by nearest expiry</div>
    </Section>
  );
}

// ============ Vol Analytics Panel ============
export function VolAnalyticsPanel({ data, loading, error }) {
  if (error) return <ErrorState error={error} />;
  if (loading) return <LoadingState />;
  if (!data?.skew && !data?.iv_rank) return <EmptyState />;
  return (
    <Section title="Volatility">
      <div className="space-y-1.5">
        {data?.skew && <>
          <div className="text-[8px] text-slate-500 uppercase tracking-wider">Skew</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
            <div className="flex justify-between"><span className="text-slate-500">ATM IV</span><span className="mono text-slate-300">{safeFixed((data.skew.atm_iv ?? 0) * 100, 1)}%</span></div>
            <div className="flex justify-between"><span className="text-slate-500">RR 25d</span><span className={`mono font-bold ${data.skew.interpretation?.risk_reversal === "bullish" ? "text-emerald-400" : data.skew.interpretation?.risk_reversal === "bearish" ? "text-rose-400" : "text-slate-300"}`}>{safeFixed((data.skew.risk_reversal_25d ?? 0) * 100, 2)}%</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Butterfly</span><span className="mono text-slate-300">{safeFixed((data.skew.butterfly_25d ?? 0) * 100, 2)}%</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Skew Slope</span><span className={`mono ${data.skew.interpretation?.skew_slope === "steep" ? "text-amber-400" : "text-slate-300"}`}>{safeFixed(data.skew.skew_slope, 2)}</span></div>
          </div>
        </>}
        {data?.iv_rank && <>
          <div className="text-[8px] text-slate-500 uppercase tracking-wider mt-1">IV Rank / RV</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
            <div className="flex justify-between"><span className="text-slate-500">IV Rank</span><span className={`mono font-bold ${data.iv_rank.interpretation === "expensive" ? "text-rose-400" : data.iv_rank.interpretation === "cheap" ? "text-emerald-400" : "text-amber-400"}`}>{data.iv_rank.iv_rank != null ? safeFixed(data.iv_rank.iv_rank * 100, 0) + "%" : "—"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">IV Pctl</span><span className="mono text-slate-300">{data.iv_rank.iv_percentile != null ? safeFixed(data.iv_rank.iv_percentile * 100, 0) + "%" : "—"}</span></div>
            {data.iv_rank.rv_close != null && <>
              <div className="flex justify-between"><span className="text-slate-500">RV 20d</span><span className="mono text-slate-300">{safeFixed(data.iv_rank.rv_close * 100, 1)}%</span></div>
              <div className="flex justify-between"><span className="text-slate-500">RV-IV</span><span className={`mono font-bold ${(data.iv_rank.rv_iv_spread || 0) > 0.05 ? "text-rose-400" : (data.iv_rank.rv_iv_spread || 0) < -0.05 ? "text-emerald-400" : "text-slate-300"}`}>{data.iv_rank.rv_iv_spread != null ? safeFixed(data.iv_rank.rv_iv_spread * 100, 1) + "%" : "—"}</span></div>
            </>}
          </div>
        </>}
        {data?.iv_surface?.term_structure?.length > 0 && <>
          <div className="text-[8px] text-slate-500 uppercase tracking-wider mt-1">Term Structure</div>
          <div className="flex gap-1 flex-wrap">
            {data.iv_surface.term_structure.slice(0, 6).map((ts, i) => (
              <div key={i} className="text-[8px] px-1.5 py-0.5 bg-slate-800 rounded"><span className="text-slate-500">{ts.dte}d</span> <span className="mono text-slate-300">{safeFixed((ts.atm_iv ?? 0) * 100, 1)}%</span></div>
            ))}
          </div>
        </>}
      </div>
    </Section>
  );
}

// ============ Greek Reference Panel ============
export function GreekReferencePanel() {
  return (
    <Section title="Greek Reference" defaultOpen={false}>
      <details className="text-[9px]">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Gamma (∂Δ/∂S)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Rate of delta change. Highest ATM near expiry. Long γ = dealers hedge against market (stabilizing). Short γ = dealers hedge with market (destabilizing).</div>
      </details>
      <details className="text-[9px] mt-1">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Vanna (∂Δ/∂σ)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Delta sensitivity to IV changes. Long vanna = IV up → delta up (selling pressure). Short vanna = IV up → delta down (buying pressure).</div>
      </details>
      <details className="text-[9px] mt-1">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Charm (∂Δ/∂t)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Delta decay per day. For 0DTE, charm is extreme. Forces hedging flows as expiry approaches.</div>
      </details>
      <details className="text-[9px] mt-1">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Vomma (∂V/∂σ)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Vega sensitivity to vol changes. High vomma = option prices explode during vol spikes.</div>
      </details>
      <details className="text-[9px] mt-1">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Zomma (∂Γ/∂σ)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Gamma sensitivity to vol changes. Vol spike → gamma increase → bigger hedging demand → more vol.</div>
      </details>
    </Section>
  );
}

// ============ Databento Usage Panel ============
export function UsagePanel() {
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchUsage = async () => {
    setLoading(true);
    setError(null);
    try {
      const base = BACKEND_URL;
      const res = await axios.get(`${base}/api/databento/usage`);
      setUsage(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Failed to fetch usage");
    }
    setLoading(false);
  };

  return (
    <Section title="Data Usage" defaultOpen={false} badge={usage ? `$${usage.total_usd}` : undefined}>
      <button onClick={fetchUsage} className="btn w-full text-[9px] mb-1" disabled={loading}>
        {loading ? "…" : "Check Usage"}
      </button>
      {error && <div className="text-[9px] text-rose-400 mb-1">{String(error)}</div>}
      {usage && (
        <div className="space-y-0.5 text-[9px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Total</span>
            <span className="mono font-bold text-slate-300">${usage.total_usd}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">OI Fetches</span>
            <span className="mono text-slate-400">${usage.est_oi_cost_usd} ({usage.oi_fetch_count})</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Live Tape</span>
            <span className="mono text-slate-400">${usage.est_tape_cost_usd} ({usage.tape_session_count})</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Credits Left</span>
            <span className="mono font-bold text-emerald-400">${usage.credits_remaining}</span>
          </div>
        </div>
      )}
    </Section>
  );
}

// ============ Live Policy Panel ============
export function LivePolicyPanel() {
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tickers, setTickers] = useState("SPY");
  const [windowStart, setWindowStart] = useState("09:00");
  const [windowStop, setWindowStop] = useState("10:30");

  const fetchPolicy = async () => {
    setLoading(true);
    setError(null);
    try {
      const base = BACKEND_URL;
      const res = await axios.get(`${base}/api/live/policy`);
      setPolicy(res.data);
      if (res.data.paid_tickers) setTickers(res.data.paid_tickers.join(", "));
      if (res.data.live_window_et) {
        setWindowStart(res.data.live_window_et.start_hhmm || "09:00");
        setWindowStop(res.data.live_window_et.stop_hhmm || "10:30");
      }
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Failed to fetch policy");
    }
    setLoading(false);
  };

  const updatePolicy = async () => {
    setLoading(true);
    setError(null);
    try {
      const base = BACKEND_URL;
      const res = await axios.post(`${base}/api/live/policy`, {
        paid_tickers: tickers.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean),
        window_start: windowStart,
        window_stop: windowStop,
      });
      setPolicy(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Failed to update policy");
    }
    setLoading(false);
  };

  const inputCls = "w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[10px] text-slate-200 focus:border-teal-500 focus:outline-none";

  return (
    <Section title="Live Policy" defaultOpen={false}>
      <button onClick={fetchPolicy} className="btn w-full text-[9px] mb-1" disabled={loading}>
        {loading ? "…" : "Load Policy"}
      </button>
      {error && <div className="text-[9px] text-rose-400 mb-1">{String(error)}</div>}
      {policy && (
        <div className="text-[9px] text-slate-400 mb-1">
          Paid: {policy.paid_tickers?.join(", ") || "—"} · Window: {policy.live_window_et?.start_hhmm}–{policy.live_window_et?.stop_hhmm} ET
        </div>
      )}
      <div className="space-y-1">
        <div>
          <div className="label mb-0.5">Paid Tickers (comma-sep)</div>
          <input className={inputCls} value={tickers} onChange={(e) => setTickers(e.target.value)} placeholder="SPY, QQQ" />
        </div>
        <div className="grid grid-cols-2 gap-1">
          <div>
            <div className="label mb-0.5">Window Start (ET)</div>
            <input className={inputCls} value={windowStart} onChange={(e) => setWindowStart(e.target.value)} />
          </div>
          <div>
            <div className="label mb-0.5">Window Stop (ET)</div>
            <input className={inputCls} value={windowStop} onChange={(e) => setWindowStop(e.target.value)} />
          </div>
        </div>
        <button onClick={updatePolicy} className="btn w-full text-[9px]" disabled={loading}>
          Update Policy
        </button>
      </div>
    </Section>
  );
}
