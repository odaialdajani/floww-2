// Pure JS — no React, no backend. ESM.
import { scanRowsToCSV } from '../scanLogic.js';

const csvCell = (v) => {
  const s = v == null || v === '—' || v === '-' ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

function headerComment({ filters, timestamp, visibleColumns } = {}) {
  const lines = [];
  lines.push('# Tidehunter Pro — flowseeker export');
  lines.push(`# exported: ${timestamp ? new Date(timestamp).toISOString() : new Date().toISOString()}`);
  if (visibleColumns && visibleColumns.length) {
    lines.push(`# visible columns: ${visibleColumns.join(', ')}`);
  }
  if (filters && typeof filters === 'object' && Object.keys(filters).length) {
    // Serialize filters honestly — no fabrication
    try { lines.push(`# filters: ${JSON.stringify(filters)}`); } catch { lines.push('# filters: [unserializable]'); }
  } else {
    lines.push('# filters: (none)');
  }
  lines.push('# premium values are estimates (~) — no quote feed on this data');
  return lines.join('\n');
}

export function buildCsvExport(rows, opts = {}) {
  const { filters, timestamp, visibleColumns } = opts;
  const comment = headerComment({ filters, timestamp, visibleColumns });

  // Delegate body to scanLogic.scanRowsToCSV when available — it handles
  // null/— escaping and ISO firstSeen. Fallback is identical logic.
  let body;
  if (typeof scanRowsToCSV === 'function') {
    body = scanRowsToCSV(rows || []);
  } else {
    const cols = ['seen','score','ticker','type','strike','expiry','dte','volume','oi','oi_chg_pct','vol_oi','premium_est','notional','iv','flow','archetype','lean','regime'];
    const head = cols.join(',');
    const lines = (rows || []).map((r) => cols.map((k) => csvCell(r[k] ?? r[k.replace(/^seen$/,'firstSeen')])).join(','));
    body = [head, ...lines].join('\n');
  }

  // If visibleColumns is given, filter body columns to that subset
  if (visibleColumns && visibleColumns.length) {
    const allLines = body.split('\n');
    const header = allLines[0].split(',');
    const idxs = visibleColumns.map((c) => header.indexOf(c)).filter((i) => i >= 0);
    if (idxs.length) {
      const filtered = allLines.map((line) => {
        // naive split — scanRowsToCSV already quoted commas
        // re-split respecting quotes
        const cells = [];
        let cur = '', inQ = false;
        for (let i = 0; i < line.length; i++) {
          const ch = line[i];
          if (ch === '"' ) { if (inQ && line[i+1] === '"') { cur += '"'; i++; } else inQ = !inQ; cur += ch; }
          else if (ch === ',' && !inQ) { cells.push(cur); cur = ''; }
          else cur += ch;
        }
        cells.push(cur);
        return idxs.map((j) => cells[j] ?? '').join(',');
      });
      body = filtered.join('\n');
    }
  }

  return `${comment}\n${body}`;
}

export function csvRowCount(csv) {
  const lines = csv.split('\n').filter((l) => l && !l.startsWith('#'));
  return Math.max(0, lines.length - 1);
}
