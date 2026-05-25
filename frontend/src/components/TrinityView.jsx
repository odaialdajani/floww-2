import React, { useEffect, useState } from "react";
import axios from "axios";
import { fmt, fmtAbs, pctClass, TRINITY } from "../lib/helpers";
import BarHeatmap from "./BarHeatmap";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function TrinityView({ onFocusTicker }) {
  const [data, setData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchAll = async () => {
      setLoading(true);
      try {
        const results = await Promise.allSettled(
          TRINITY.map(t => axios.get(`${API}/heatmap/${t}?expiries=3&mode=day`).then(r => ({ ticker: t, data: r.data })))
        );
        const newData = {};
        results.forEach(r => {
          if (r.status === "fulfilled") newData[r.value.ticker] = r.value.data;
          else if (r.status === "rejected") {
            const ticker = TRINITY[results.indexOf(r)];
            newData[ticker] = { error: r.reason?.message || "Failed" };
          }
        });
        if (mounted) { setData(newData); setLoading(false); }
      } catch (e) {
        if (mounted) { setError(e.message); setLoading(false); }
      }
    };
    fetchAll();
    const id = setInterval(fetchAll, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  if (loading && Object.keys(data).length === 0) return <div className="p-4 text-slate-500 text-sm">Loading Trinity...</div>;
  if (error) return <div className="p-4 text-rose-400 text-sm">Error: {error}</div>;

  return (
    <div className="space-y-3">
      {/* Confluence Summary */}
      <ConfluenceSummary data={data} />
      {/* Three ticker cards */}
      <div className="grid grid-cols-3 gap-3" style={{ minHeight: 0 }}>
        {TRINITY.map(t => (
          <TrinityCard key={t} ticker={t} data={data[t]} onFocus={() => onFocusTicker && onFocusTicker(t)} />
        ))}
      </div>
    </div>
  );
}

function ConfluenceSummary({ data }) {
  const tickers = TRINITY.map(t => data[t]).filter(d => d && !d.error);
  if (tickers.length === 0) return null;

  const regimes = tickers.map(d => d.nodes?.regime).filter(Boolean);
  const allSame = regimes.length > 0 && regimes.every(r => r === regimes[0]);
  const confluence = regimes.length > 0 ? regimes.filter(r => r === regimes[0]).length / regimes.length : 0;

  const biases = [];
  tickers.forEach(d => (d.patterns || []).forEach(p => biases.push(p.bias)));
  const uniqueBiases = [...new Set(biases)];

  const verdict = confluence === 1 ? "full_alignment" : confluence >= 0.66 ? "partial_alignment" : "divergence";
  const verdictColor = verdict === "full_alignment" ? "text-emerald-400" : verdict === "partial_alignment" ? "text-amber-400" : "text-rose-400";
  const verdictText = verdict === "full_alignment" ? "All three agree. Highest conviction." : verdict === "partial_alignment" ? "Two-of-three. Reduced size." : "Disagreement. Wait.";

  return (
    <div className="panel p-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div>
            <div className="label">Confluence</div>
            <div className="text-sm mono">
              <span className={confluence === 1 ? "text-emerald-400" : confluence >= 0.66 ? "text-amber-400" : "text-rose-400"}>
                {(confluence * 100).toFixed(0)}%
              </span>
              <span className="text-slate-500"> alignment</span>
            </div>
          </div>
          <div className="dotted-divider h-6" style={{ width: 1 }} />
          <div>
            <div className="label">Regime</div>
            <div className="text-sm mono">
              <span className={regimes[0] === "positive" ? "text-emerald-400" : regimes[0] === "negative" ? "text-rose-400" : "text-slate-400"}>
                {regimes[0] || "—"}
              </span>
            </div>
          </div>
          {uniqueBiases.length > 0 && <>
            <div className="dotted-divider h-6" style={{ width: 1 }} />
            <div>
              <div className="label">Biases</div>
              <div className="flex gap-1">
                {uniqueBiases.map(b => (
                  <span key={b} className="text-[8px] px-1 py-px border border-slate-700 rounded uppercase tracking-wider text-slate-400">{b}</span>
                ))}
              </div>
            </div>
          </>}
        </div>
        <div className={`text-[10px] uppercase tracking-widest font-bold ${verdictColor}`}>
          {verdictText}
        </div>
      </div>
    </div>
  );
}

function TrinityCard({ ticker, data, onFocus }) {
  if (!data || data.error) {
    return (
      <div className="panel p-3">
        <div className="flex justify-between items-baseline mb-1">
          <div className="font-bold text-xs">{ticker.replace("^", "")}</div>
          <div className="text-[9px] text-rose-400">{data?.error || "No data"}</div>
        </div>
      </div>
    );
  }

  const { spot, nodes, implied_move } = data;
  const regime = nodes?.regime || "—";
  const regimeColor = regime === "positive" ? "text-emerald-400" : regime === "negative" ? "text-rose-400" : "text-slate-400";
  const patterns = (data.patterns || []).slice(0, 3);

  return (
    <div className="panel p-3 flex flex-col" style={{ minHeight: 0, maxHeight: "50vh" }}>
      <div className="flex justify-between items-baseline mb-1 flex-shrink-0">
        <div className="font-bold text-xs">{ticker.replace("^", "")}</div>
        <div className="text-[9px] mono text-slate-400">spot {fmt(spot, 1)} · <span className={regimeColor}>{regime}γ</span></div>
      </div>
      <div className="mb-1 overflow-auto" style={{ flex: 1, minHeight: 0 }} id={`trinity-bar-${ticker.replace("^", "")}`}>
        <BarHeatmap data={data} filters={{}} compact />
      </div>
      <div className="flex flex-wrap gap-0.5 mt-1">
        {patterns.map((p, i) => (
          <span key={i} className="text-[8px] px-1 py-px border border-slate-700 rounded uppercase tracking-wider text-slate-400">{p.name}</span>
        ))}
      </div>
      {implied_move && (
        <div className="text-[8px] text-slate-500 mt-1">
          ±{implied_move.implied_move_pct}% · {fmt(implied_move.lower_range, 0)}–{fmt(implied_move.upper_range, 0)}
        </div>
      )}
      <button className="text-[8px] text-teal-400 underline mt-1 text-left" onClick={onFocus}>focus →</button>
    </div>
  );
}
