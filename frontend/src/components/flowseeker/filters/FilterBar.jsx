import React from 'react';
import { applyFilters, widenActions } from './filterState.js';

export default function FilterBar({ filters, onChange, beforeCount, afterCount }) {
  const acts = widenActions(filters);
  const empty = afterCount === 0 && beforeCount > 0;
  return (
    <div className="fsb-filters" data-testid="filter-bar">
      <label data-testid="filter-sweeps"><input type="checkbox" checked={!!filters.sweepsOnly} onChange={(e) => onChange({ ...filters, sweepsOnly: e.target.checked })} /> Sweeps only <span className="fsb-filter__proxy">(proxy)</span></label>
      <label data-testid="filter-bid"><input type="checkbox" checked={!!filters.side?.BID} onChange={(e) => onChange({ ...filters, side: { ...filters.side, BID: e.target.checked } })} /> Bid</label>
      <label data-testid="filter-mid"><input type="checkbox" checked={!!filters.side?.MID} onChange={(e) => onChange({ ...filters, side: { ...filters.side, MID: e.target.checked } })} /> Mid</label>
      <label data-testid="filter-ask"><input type="checkbox" checked={!!filters.side?.ASK} onChange={(e) => onChange({ ...filters, side: { ...filters.side, ASK: e.target.checked } })} /> Ask</label>
      <label data-testid="filter-otm"><input type="checkbox" checked={!!filters.otm} onChange={(e) => onChange({ ...filters, otm: e.target.checked })} /> OTM</label>
      <label data-testid="filter-itm"><input type="checkbox" checked={!!filters.itm} onChange={(e) => onChange({ ...filters, itm: e.target.checked })} /> ITM</label>
      <label data-testid="filter-0dte"><input type="checkbox" checked={!!filters.dte0} onChange={(e) => onChange({ ...filters, dte0: e.target.checked })} /> 0DTE</label>
      <label data-testid="filter-opex"><input type="checkbox" checked={!!filters.opexOnly} onChange={(e) => onChange({ ...filters, opexOnly: e.target.checked })} /> OPEX only</label>
      <label data-testid="filter-stocks"><input type="checkbox" checked={!!filters.equityType?.stocks} onChange={(e) => onChange({ ...filters, equityType: { ...filters.equityType, stocks: e.target.checked } })} /> Stocks</label>
      <label data-testid="filter-etfs"><input type="checkbox" checked={!!filters.equityType?.etfs} onChange={(e) => onChange({ ...filters, equityType: { ...filters.equityType, etfs: e.target.checked } })} /> ETFs</label>
      <label data-testid="filter-indices"><input type="checkbox" checked={!!filters.equityType?.indices} onChange={(e) => onChange({ ...filters, equityType: { ...filters.equityType, indices: e.target.checked } })} /> Indices</label>
      <label data-testid="filter-abs"><input type="checkbox" checked={!!filters.absScore} onChange={(e) => onChange({ ...filters, absScore: e.target.checked })} /> |score|</label>
      <span data-testid="filter-counts">{beforeCount} → {afterCount}</span>
      {empty && (
        <div data-testid="filter-empty">
          <span>0 rows — widen shortage</span>
          {acts.map((a) => <button key={a.action} data-testid={`widen-${a.action}`} onClick={() => onChange(applyWiden(filters, a.action))}>{a.label}</button>)}
        </div>
      )}
    </div>
  );
}

function applyWiden(f, action) {
  const n = { ...f, equityType: { ...f.equityType }, side: { ...f.side } };
  if (action === 'lower_premium') n.minPremium = 0;
  if (action === 'enable_etfs') n.equityType.etfs = true;
  if (action === 'clear_sweep') n.sweepsOnly = false;
  if (action === 'lower_score') n.minScore = 0;
  if (action === 'clear_dte') { n.dte0 = false; n.opexOnly = false; n.dteBand = null; }
  if (action === 'reset') return { ...n, sweepsOnly: false, dte0: false, opexOnly: false, minPremium: 0, minScore: 0, dteBand: null, equityType: { stocks: true, etfs: true, indices: true } };
  return n;
}
