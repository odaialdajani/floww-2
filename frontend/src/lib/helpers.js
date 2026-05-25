// ============ Formatting Helpers ============

export const fmt = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });

export const fmtAbs = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toFixed(0);
};

export const fmtCell = (v) => {
  if (v === null || v === undefined || isNaN(v) || v === 0) return "";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  let s;
  if (a >= 1e6) s = (a / 1e6).toFixed(2) + "M";
  else if (a >= 1e3) s = (a / 1e3).toFixed(1) + "K";
  else s = a.toFixed(0);
  return sign + "$" + s;
};

export const pctClass = (v) => v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-slate-400";

export const tagFor = (kind) => ({
  king: "tag king", floor: "tag floor", ceiling: "tag ceiling", gate: "tag gate", air: "tag air",
  fresh: "tag fresh", tested: "tag tested", delivered: "tag delivered", decaying: "tag decaying",
}[kind] || "tag");

export const expFmt = (e) => { try { const [, m, d] = e.split("-"); return `${m}-${d}`; } catch { return e; } };

// ============ Color Scale ============
// Skylit-style: positive (Pika) = cyan/teal, negative (Barney) = purple/violet
// King highlights pop yellow-green. VEX uses warmer tones (amber/pink). Charm uses cyan/violet.
export function cellColor(v, maxAbs, isKing = false, mode = "gex") {
  if (!v || maxAbs === 0) return { bg: "rgba(15, 22, 32, 0.7)", text: "#5a6781" };
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  if (mode === "charm") {
    if (isKing && v > 0) return { bg: `rgba(34, 211, 238, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (isKing && v < 0) return { bg: `rgba(168, 85, 247, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (v > 0) { const alpha = 0.15 + 0.7 * norm; return { bg: `rgba(34, 211, 238, ${alpha})`, text: norm > 0.5 ? "#0b1320" : "#a5f3fc" }; }
    else { const alpha = 0.18 + 0.7 * norm; return { bg: `rgba(168, 85, 247, ${alpha})`, text: norm > 0.5 ? "#fdf4ff" : "#e9d5ff" }; }
  }
  if (mode === "vex") {
    if (isKing && v > 0) return { bg: `rgba(251, 191, 36, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (isKing && v < 0) return { bg: `rgba(219, 39, 119, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (v > 0) { const alpha = 0.15 + 0.7 * norm; return { bg: `rgba(245, 158, 11, ${alpha})`, text: norm > 0.5 ? "#0b1320" : "#fcd34d" }; }
    else { const alpha = 0.18 + 0.7 * norm; return { bg: `rgba(219, 39, 119, ${alpha})`, text: norm > 0.5 ? "#fdf4ff" : "#f9a8d4" }; }
  }
  if (isKing && v > 0) return { bg: `rgba(190, 242, 100, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
  if (isKing && v < 0) return { bg: `rgba(232, 121, 249, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
  if (v > 0) { const alpha = 0.15 + 0.7 * norm; return { bg: `rgba(45, 212, 191, ${alpha})`, text: norm > 0.5 ? "#0b1320" : "#a7f3d0" }; }
  else { const alpha = 0.18 + 0.7 * norm; return { bg: `rgba(168, 85, 247, ${alpha})`, text: norm > 0.5 ? "#fdf4ff" : "#e9d5ff" }; }
}

// ============ Constants ============
export const TRINITY = ["^SPX", "SPY", "QQQ"];
export const DEFAULT_TICKERS = ["SPY", "QQQ", "^SPX", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "NFLX", "AMD", "SMH", "XLF", "GLD"];
export const REFRESH_MS = 30000;
