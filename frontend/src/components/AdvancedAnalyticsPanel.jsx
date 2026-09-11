import React from "react";
import { fmt, fmtAbs } from "../lib/helpers";

// ============ Shared Null-Safe Helpers ============
const dash = (v, fn) => (v == null ? "—" : (fn ? fn(v) : v));
const sn = (v) => (v != null && !isNaN(Number(v)) ? Number(v) : 0);
const safeFixed = (v, d) => (v != null && !isNaN(v)) ? v.toFixed(d) : "—";

// ============ State Wrapper ============
function StateWrap({ loading, error, empty, children, label }) {
  if (loading) return (
    <div className="panel-2 p-2">
      <div className="label mb-0">{label}</div>
      <div className="text-[9px] text-slate-500 mt-1">Loading…</div>
    </div>
  );
  if (error) return (
    <div className="panel-2 p-2">
      <div className="label mb-0">{label}</div>
      <div className="text-[9px] text-amber-400/70 mt-1">Unavailable</div>
    </div>
  );
  if (empty) return (
    <div className="panel-2 p-2">
      <div className="label mb-0">{label}</div>
      <div className="text-[9px] text-slate-500 mt-1">No data</div>
    </div>
  );
  return children;
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

// ============ Mini Bar Chart ============
function MiniBar({ value, max, color = "teal", label }) {
  const sv = sn(value);
  const sm = sn(max);
  const pct = sm > 0 ? Math.min(100, Math.abs(sv) / sm * 100) : 0;
  const barColor = color === "teal" ? "bg-teal-500/60" : color === "rose" ? "bg-rose-500/60" : color === "amber" ? "bg-amber-500/60" : "bg-sky-500/60";
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="text-slate-500 w-14 text-right truncate font-medium" title={label}>{label}</span>
      <div className="flex-1 h-2 bg-slate-800/60 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="mono text-slate-300 w-14 text-right">{typeof value === "number" ? safeFixed(value, 2) : value}</span>
    </div>
  );
}

// ============ Market Regime Panel ============
export function MarketRegimePanel({ data, loading, error }) {
  const empty = !data?.market_regime;
  const mr = data?.market_regime;
  const regimeColor = mr?.regime === "calm" ? "text-emerald-400" : mr?.regime === "normal" ? "text-sky-400" : mr?.regime === "stressed" ? "text-amber-400" : "text-rose-400";
  const regimeBg = mr?.regime === "calm" ? "bg-emerald-500/10 border-emerald-500/30" : mr?.regime === "normal" ? "bg-sky-500/10 border-sky-500/30" : mr?.regime === "stressed" ? "bg-amber-500/10 border-amber-500/30" : "bg-rose-500/10 border-rose-500/30";

  return (
    <StateWrap loading={loading} error={error} empty={empty} label="Regime">
      <Section title="Regime" badge={dash(mr?.regime, r => r.toUpperCase())}>
        <div className={`text-[9px] p-1.5 rounded border ${regimeBg} mb-1.5`}>
          <div className={`font-bold text-[11px] ${regimeColor}`}>{dash(mr?.regime, r => r.toUpperCase())}</div>
          <div className="text-slate-400 mt-0.5">
            {dash(mr?.interpretation?.fear_greed, f => f.replace("_", " "))} · {dash(mr?.interpretation?.tail_risk)} tails
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
          <div className="flex justify-between"><span className="text-slate-500">ATM IV</span><span className="mono text-slate-300">{dash(sn(mr?.atm_iv) * 100, v => safeFixed(v, 1) + "%")}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Skew</span><span className={`mono ${sn(mr?.skew) > 0.02 ? "text-rose-400" : sn(mr?.skew) < -0.02 ? "text-emerald-400" : "text-slate-300"}`}>{dash(sn(mr?.skew) * 100, v => safeFixed(v, 2) + "%")}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Daily Move</span><span className="mono text-slate-300">±{dash(mr?.expected_daily_spot_move_pct)}%</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Vol of Vol</span><span className="mono text-slate-300">{dash(sn(mr?.implied_vol_of_vol) * 100, v => safeFixed(v, 1) + "%")}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Spot-Vol ρ</span><span className="mono text-slate-300">{dash(sn(mr?.implied_spot_vol_corr), v => safeFixed(v, 2))}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Curvature</span><span className="mono text-slate-300">{dash(sn(mr?.curvature) * 100, v => safeFixed(v, 2) + "%")}</span></div>
        </div>
      </Section>
    </StateWrap>
  );
}

// ============ Implied PDF Panel ============
export function ImpliedPDFPanel({ data, loading, error }) {
  const pdf = data?.implied_pdf;
  const probs = pdf?.strike_probabilities?.filter(p => p.probability > 0);
  const empty = !probs?.length;
  const spot = sn(data?.spot);
  const maxProb = probs?.length ? Math.max(...probs.map(p => sn(p.probability))) : 0;

  return (
    <StateWrap loading={loading} error={error} empty={empty} label="Implied PDF">
      <Section title="Implied PDF" badge={dash(pdf?.expiry, e => e.slice(5))}>
        <div className="text-[9px] p-1.5 rounded bg-slate-800/50 border border-slate-700/50 mb-1.5">
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
            <div><span className="text-slate-500">Mode: </span><span className="mono text-amber-300 font-bold">{dash(pdf?.most_likely_price, p => fmt(p, 0))}</span></div>
            <div><span className="text-slate-500">Median: </span><span className="mono text-slate-300">{dash(pdf?.median_price, p => fmt(p, 0))}</span></div>
            <div><span className="text-slate-500">E[Move]: </span><span className="mono text-slate-300">±{dash(pdf?.expected_move_pct)}%</span></div>
            <div><span className="text-slate-500">Skew: </span><span className={`mono ${pdf?.interpretation?.skew === "bullish" ? "text-emerald-400" : pdf?.interpretation?.skew === "bearish" ? "text-rose-400" : "text-slate-300"}`}>{dash(pdf?.interpretation?.skew)}</span></div>
            <div><span className="text-slate-500">P(≤spot): </span><span className="mono text-slate-300">{dash(sn(pdf?.cumulative_below_spot) * 100, v => safeFixed(v, 1) + "%")}</span></div>
            <div><span className="text-slate-500">P(1σ): </span><span className="mono text-slate-300">{dash(sn(pdf?.prob_within_1sd) * 100, v => safeFixed(v, 1) + "%")}</span></div>
          </div>
        </div>
        <div className="space-y-0.5 max-h-24 overflow-y-auto">
          {probs?.slice(0, 20).map((p, i) => (
            <MiniBar key={i} value={sn(p.probability)} max={maxProb} label={fmt(p.strike, 0)} color={sn(p.strike) >= spot ? "teal" : "rose"} />
          ))}
        </div>
        <div className="text-[8px] text-slate-600 mt-1">Risk-neutral density · {dash(pdf?.interpretation?.conviction)} conviction</div>
      </Section>
    </StateWrap>
  );
}

// ============ Hedge Impulse Panel ============
export function HedgeImpulsePanel({ data, loading, error }) {
  const hi = data?.hedge_impulse;
  const empty = !hi?.curve?.length;
  const spot = sn(data?.spot);

  const regimeColor = hi?.regime === "pinned" ? "text-emerald-400" : hi?.regime === "expansion" ? "text-rose-400" : hi?.regime === "squeeze-up" ? "text-sky-400" : hi?.regime === "squeeze-down" ? "text-amber-400" : "text-slate-400";

  const impulses = hi?.curve?.map(p => p.impulse).filter(v => v != null && !isNaN(v)) || [];
  const maxImp = Math.max(...impulses.map(Math.abs), 1);

  const regimeDesc = !hi?.regime || hi.regime === "mixed" ? "Mixed signals"
    : hi.regime === "pinned" ? "Strong mean-reversion at spot"
    : hi.regime === "expansion" ? "Negative gamma — breakout likely"
    : hi.regime === "squeeze-up" ? "Upside acceleration bias"
    : hi.regime === "squeeze-down" ? "Downside acceleration bias"
    : "Mixed signals";

  return (
    <StateWrap loading={loading} error={error} empty={empty} label="Hedge Impulse">
      <Section title="Hedge Impulse" badge={dash(hi?.regime)}>
        <div className={`text-[9px] p-1.5 rounded border mb-1.5 ${hi?.regime === "pinned" ? "bg-emerald-500/10 border-emerald-500/30" : hi?.regime === "expansion" ? "bg-rose-500/10 border-rose-500/30" : "bg-slate-800/50 border-slate-700/50"}`}>
          <div className={`font-bold ${regimeColor}`}>{dash(hi?.regime, r => r.replace("-", " ").toUpperCase())}</div>
          <div className="text-slate-400 mt-0.5">{regimeDesc}</div>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px] mb-1">
          <div className="flex justify-between"><span className="text-slate-500">H(spot)</span><span className={`mono font-bold ${sn(hi?.impulse_at_spot) > 0 ? "text-emerald-400" : "text-rose-400"}`}>{dash(sn(hi?.impulse_at_spot), v => safeFixed(v, 0))}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">k (coupling)</span><span className="mono text-slate-300">{dash(sn(hi?.spot_vol_coupling), v => safeFixed(v, 1))}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Attractor ↑</span><span className="mono text-emerald-400">{dash(hi?.nearest_attractor_above, a => fmt(a, 0))}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Attractor ↓</span><span className="mono text-rose-400">{dash(hi?.nearest_attractor_below, a => fmt(a, 0))}</span></div>
        </div>
        <div className="space-y-0.5 max-h-20 overflow-y-auto">
          {hi?.curve?.filter((_, i) => i % 2 === 0).map((p, i) => (
            <MiniBar key={i} value={sn(p.impulse)} max={maxImp} label={fmt(p.price, 0)} color={sn(p.impulse) >= 0 ? "teal" : "rose"} />
          ))}
        </div>
        <div className="text-[8px] text-slate-600 mt-1">H(S) = Γ(S) - (k/S)·V(S) · Positive = mean-reverting</div>
      </Section>
    </StateWrap>
  );
}

// ============ Pressure Cloud Panel ============
export function PressureCloudPanel({ data, loading, error }) {
  const pc = data?.pressure_cloud;
  const zones = [
    ...pc?.stability_zones?.map(z => ({ ...z, type: "stability" })) || [],
    ...pc?.acceleration_zones?.map(z => ({ ...z, type: "acceleration" })) || [],
  ].sort((a, b) => sn(b.strength) - sn(a.strength));

  const empty = !zones.length && !pc?.regime_edges?.length;

  return (
    <StateWrap loading={loading} error={error} empty={empty} label="Pressure Cloud">
      <Section title="Pressure Cloud" badge={`${zones.length}`}>
        <div className="space-y-1">
          {zones.slice(0, 4).map((z, i) => (
            <div key={i} className={`text-[9px] p-1 rounded border-l-2 ${z.type === "stability" ? "border-emerald-500 bg-emerald-500/5" : "border-rose-500 bg-rose-500/5"}`}>
              <div className="flex justify-between items-center">
                <span className={`font-bold ${z.type === "stability" ? "text-emerald-400" : "text-rose-400"}`}>
                  {z.type === "stability" ? "STABILITY" : "ACCELERATION"}
                </span>
                <span className="text-slate-500">{dash(z.side)} · {dash(sn(z.strength) * 100, v => safeFixed(v, 0) + "%")}</span>
              </div>
              <div className="flex gap-2 mt-0.5 text-[8px]">
                <span className="text-slate-500">center: <span className="mono text-slate-300">{dash(z.center, c => fmt(c, 0))}</span></span>
                <span className="text-slate-500">trade: <span className={z.trade_type === "long" ? "text-emerald-400" : "text-rose-400"}>{dash(z.trade_type)}</span></span>
                <span className="text-slate-500">{dash(z.hedge_type)}</span>
              </div>
            </div>
          ))}
          {pc?.regime_edges?.length > 0 && (
            <div className="text-[8px] text-slate-500 mt-1">
              Regime edges: {pc.regime_edges.map(e => dash(e.price, p => fmt(p, 0))).join(", ")}
            </div>
          )}
        </div>
        <div className="text-[8px] text-slate-600 mt-1">Dealer hedge flow zones · Green = bounce · Red = momentum</div>
      </Section>
    </StateWrap>
  );
}

// ============ Charm Integral Panel ============
export function CharmIntegralPanel({ data, loading, error }) {
  const ci = data?.charm_integral;
  const empty = !ci?.total_charm_to_close && ci?.total_charm_to_close !== 0;

  const dirColor = ci?.direction === "buying" ? "text-emerald-400" : ci?.direction === "selling" ? "text-rose-400" : "text-slate-400";

  return (
    <StateWrap loading={loading} error={error} empty={empty} label="Charm Integral">
      <Section title="Charm Integral" badge={dash(ci?.expiry, e => e.slice(5))}>
        <div className={`text-[9px] p-1.5 rounded border mb-1.5 ${ci?.direction === "buying" ? "bg-emerald-500/10 border-emerald-500/30" : ci?.direction === "selling" ? "bg-rose-500/10 border-rose-500/30" : "bg-slate-800/50 border-slate-700/50"}`}>
          <div className={`font-bold ${dirColor}`}>{dash(ci?.direction, d => d.toUpperCase())}</div>
          <div className="text-slate-400 mt-0.5">Time decay pressure to close</div>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
          <div className="flex justify-between"><span className="text-slate-500">Total</span><span className={`mono font-bold ${dirColor}`}>{dash(sn(ci?.total_charm_to_close), v => safeFixed(v, 0))}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">DTE</span><span className="mono text-slate-300">{dash(ci?.days_remaining)}d</span></div>
        </div>
        {ci?.buckets?.length > 0 && (
          <div className="mt-1 space-y-0.5 max-h-16 overflow-y-auto">
            {ci.buckets.slice(0, 6).map((b, i) => (
              <MiniBar key={i} value={sn(b.cumulative_charm)} max={sn(Math.abs(ci.total_charm_to_close)) || 1} label={`${dash(b.minutes_remaining)}m`} color={sn(b.cumulative_charm) >= 0 ? "teal" : "rose"} />
            ))}
          </div>
        )}
        <div className="text-[8px] text-slate-600 mt-1">Cumulative charm exposure · Accelerates near expiry</div>
      </Section>
    </StateWrap>
  );
}
