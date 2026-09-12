import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { fmt, TRIAD, DEFAULT_TICKERS } from "../lib/helpers";
import { API as BACKEND_API } from "../config/api";

const API = BACKEND_API;

/**
 * Multi-Ticker Heatmap — Zenith reference style
 *
 * Rows = SPY strike prices (descending)
 * Columns = GEX | VEX | AMD | AMZN | GOOGL | ...
 * Each cell shows the Net GEX for that ticker at that strike.
 *
 * Reference image shows:
 * - First two columns: GEX and VEX aggregate indicators
 * - Subsequent columns: individual tickers
 * - Current price row: white background with black text
 * - Yellow cell: Point of Control (max value)
 * - Percentage badges in some cells
 */

function cellColor(v, maxAbs) {
  if (v === null || v === undefined || isNaN(v) || v === 0) {
    return { bg: "rgba(11, 17, 33, 0.95)", text: "#3a4560" };
  }
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  const isNeg = v < 0;

  // Yellow for extreme (top 10%)
  if (norm > 0.85) {
    return isNeg
      ? { bg: `rgba(168, 55, 230, ${0.5 + 0.35 * norm})`, text: "#fce7fe", star: true }
      : { bg: `rgba(251, 191, 36, ${0.7 + 0.2 * norm})`, text: "#0b1121", star: true };
  }

  if (!isNeg) {
    if (norm > 0.50) return { bg: `rgba(45, 212, 191, ${0.45 + 0.35 * norm})`, text: "#0b1121" };
    if (norm > 0.25) return { bg: `rgba(45, 212, 191, ${0.18 + 0.4 * norm})`, text: "#a7f3d0" };
    if (norm > 0.08) return { bg: `rgba(22, 78, 99, ${0.12 + 0.25 * norm})`, text: "#6ee7b7" };
    return { bg: `rgba(22, 78, 99, 0.08)`, text: "#5eead4" };
  }

  // Negative: purple backgrounds with pink/red text
  if (norm > 0.50) return { bg: `rgba(168, 85, 247, ${0.35 + 0.35 * norm})`, text: "#f9a8d4" };
  if (norm > 0.25) return { bg: `rgba(168, 85, 247, ${0.18 + 0.35 * norm})`, text: "#d8b4fe" };
  if (norm > 0.08) return { bg: `rgba(88, 28, 135, ${0.12 + 0.25 * norm})`, text: "#c4b5fd" };
  return { bg: `rgba(88, 28, 135, 0.08)`, text: "#a78bfa" };
}

function fmtCell(v) {
  if (v === null || v === undefined || isNaN(v) || v === 0) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e6) return sign + (a / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return sign + (a / 1e3).toFixed(0) + "K";
  return sign + a.toFixed(0);
}

export default function MultiTickerHeatmap({ tickers }) {
  const [allData, setAllData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const selectedTickers = useMemo(() => {
    // Featured sets ONLY (trinity + default): `popular` carries the 12k
    // full universe since 2026-09-12, so slicing it would render 20 random
    // micro-caps and fire 20 junk heatmap fetches.
    const featured = [...(tickers?.trinity || []), ...(tickers?.default || [])];
    const list = (featured.length > 0 ? featured : DEFAULT_TICKERS).slice(0, 20);
    if (!list.includes("SPY")) list.unshift("SPY");
    return [...new Set(list)];
  }, [tickers]);

  const refTicker = "SPY";

  useEffect(() => {
    let mounted = true;
    const fetchAll = async () => {
      setLoading(true);
      setError(null);
      try {
        const results = await Promise.allSettled(
          selectedTickers.map(t =>
            axios.get(`${API}/heatmap/${t}?expiries=3&mode=day`, { timeout: 15000 })
              .then(r => ({ ticker: t, data: r.data }))
          )
        );
        const newData = {};
        results.forEach(r => {
          if (r.status === "fulfilled") {
            newData[r.value.ticker] = r.value.data;
          }
        });
        if (mounted) {
          setAllData(newData);
          setLoading(false);
        }
      } catch (e) {
        if (mounted) { setError(e.message); setLoading(false); }
      }
    };
    fetchAll();
    const id = setInterval(fetchAll, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, [selectedTickers.join(",")]);

  const strikes = useMemo(() => {
    const ref = allData[refTicker];
    if (!ref?.strikes) return [];
    return ref.strikes
      .filter(s => s.strike != null)
      .sort((a, b) => b.strike - a.strike)
      .map(s => s.strike);
  }, [allData, refTicker]);

  const spot = allData[refTicker]?.spot;

  const spotRowIdx = useMemo(() => {
    if (!spot || !strikes.length) return -1;
    let bestIdx = 0;
    let bestDist = Math.abs(strikes[0] - spot);
    for (let i = 1; i < strikes.length; i++) {
      const d = Math.abs(strikes[i] - spot);
      if (d < bestDist) { bestDist = d; bestIdx = i; }
    }
    return bestIdx;
  }, [strikes, spot]);

  // Max abs across all tickers for color scaling
  const maxAbs = useMemo(() => {
    let m = 1;
    for (const t of selectedTickers) {
      const d = allData[t];
      if (!d?.strikes) continue;
      for (const s of d.strikes) {
        const v = Math.abs(s.gex || 0);
        if (v > m) m = v;
      }
    }
    return m;
  }, [allData, selectedTickers]);

  // Find POC cell (single max value across all tickers and strikes)
  const pocCell = useMemo(() => {
    let maxVal = 0;
    let pocRI = -1, pocCI = -1, pocTicker = null;
    strikes.forEach((strike, ri) => {
      selectedTickers.forEach((t, ci) => {
        const d = allData[t];
        if (!d?.strikes) return;
        const s = d.strikes.find(s2 => s2.strike === strike);
        const v = Math.abs(s?.gex || 0);
        if (v > maxVal) {
          maxVal = v;
          pocRI = ri;
          pocCI = ci;
          pocTicker = t;
        }
      });
    });
    return { rowIdx: pocRI, colIdx: pocCI, ticker: pocTicker };
  }, [allData, selectedTickers, strikes]);

  // Aggregate GEX and VEX for the first two columns
  const aggGex = useMemo(() => {
    const map = {};
    strikes.forEach(strike => {
      let sum = 0;
      selectedTickers.forEach(t => {
        const d = allData[t];
        if (!d?.strikes) return;
        const s = d.strikes.find(s2 => s2.strike === strike);
        sum += (s?.gex || 0);
      });
      map[strike] = sum;
    });
    return map;
  }, [allData, selectedTickers, strikes]);

  const aggVex = useMemo(() => {
    const map = {};
    strikes.forEach(strike => {
      let sum = 0;
      selectedTickers.forEach(t => {
        const d = allData[t];
        if (!d?.strikes) return;
        const s = d.strikes.find(s2 => s2.strike === strike);
        sum += (s?.vex || 0);
      });
      map[strike] = sum;
    });
    return map;
  }, [allData, selectedTickers, strikes]);

  const getGex = (ticker, strike) => {
    const d = allData[ticker];
    if (!d?.strikes) return 0;
    const s = d.strikes.find(s2 => s2.strike === strike);
    return s ? (s.gex || 0) : 0;
  };

  // Percentage of max for showing badges
  const getPct = (val) => {
    if (!maxAbs || !val) return 0;
    return Math.abs(val) / maxAbs * 100;
  };

  if (loading && Object.keys(allData).length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-slate-500 text-xs">Loading multi-ticker data…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-rose-400 text-xs">Error: {error}</span>
      </div>
    );
  }

  if (!strikes.length) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-slate-500 text-xs">No data available</span>
      </div>
    );
  }

  return (
    <div className="multi-heatmap-container" data-testid="multi-ticker-heatmap">
      <table className="multi-heatmap-table">
        <tbody>
          {strikes.map((strike, i) => {
            const isCurrent = i === spotRowIdx;
            return (
              <tr key={strike} className={`multi-row${isCurrent ? " multi-current-row" : ""}`}>
                {/* Price axis */}
                <td className={`multi-price-cell${isCurrent ? " multi-current-price" : ""}`}>
                  {strike >= 1000 ? fmt(strike, 0) : fmt(strike, 1)}
                </td>

                {/* Aggregate GEX column */}
                {(() => {
                  const val = aggGex[strike] || 0;
                  const cc = cellColor(val, maxAbs);
                  const isPoc = i === pocCell.rowIdx && pocCell.ticker === "__agg_gex__";
                  const pct = getPct(val);
                  return (
                    <td className="multi-data-cell" style={{ background: cc.bg, color: cc.text }}>
                      <div className="multi-cell-inner">
                        {fmtCell(val)}
                        {pct > 30 && <span className={`multi-pct${val >= 0 ? " multi-pct-pos" : " multi-pct-neg"}`}>{val >= 0 ? "+" : ""}{pct.toFixed(0)}%</span>}
                      </div>
                    </td>
                  );
                })()}

                {/* Aggregate VEX column */}
                {(() => {
                  const val = aggVex[strike] || 0;
                  const cc = cellColor(val, maxAbs);
                  const pct = getPct(val);
                  return (
                    <td className="multi-data-cell" style={{ background: cc.bg, color: cc.text }}>
                      <div className="multi-cell-inner">
                        {fmtCell(val)}
                        {pct > 30 && <span className={`multi-pct${val >= 0 ? " multi-pct-pos" : " multi-pct-neg"}`}>{val >= 0 ? "+" : ""}{pct.toFixed(0)}%</span>}
                      </div>
                    </td>
                  );
                })()}

                {/* Ticker columns */}
                {selectedTickers.map((t, ci) => {
                  const val = getGex(t, strike);
                  const cc = cellColor(val, maxAbs);
                  const isPoc = i === pocCell.rowIdx && ci === pocCell.colIdx;
                  const pct = getPct(val);
                  return (
                    <td
                      key={t}
                      className={`multi-data-cell${isPoc ? " multi-poc-cell" : ""}`}
                      style={{
                        background: isPoc ? "rgba(251, 191, 36, 0.85)" : cc.bg,
                        color: isPoc ? "#0b1121" : cc.text,
                      }}
                      title={`${t} @ ${strike}: Net GEX ${fmtCell(val)}`}
                    >
                      <div className="multi-cell-inner">
                        {isPoc ? <span className="multi-star">★</span> : null}
                        {fmtCell(val)}
                        {pct > 30 && (
                          <span className={`multi-pct${val >= 0 ? " multi-pct-pos" : " multi-pct-neg"}`}>
                            {val >= 0 ? "+" : ""}{pct.toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
