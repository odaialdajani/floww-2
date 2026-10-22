import React, { useEffect, useMemo, useRef, useState } from "react";
import { API } from "../../config/api";
import { useScopedReading } from "../../hooks/useScopedReading";
import TriadExposure from "./TriadExposure";
import TriadChainTable, { admitContracts, ContractClocks } from "./TriadChainTable";
import './WallDesk.css';

const expiriesUrl = ticker =>
  `${API}/solstice/price-paths/expiries?ticker=${encodeURIComponent(ticker)}&min_dte=0&max_dte=7&expirations=12`;
const chainUrl = (ticker, expiry) =>
  `${API}/public/chain/${encodeURIComponent(ticker)}?expiration=${encodeURIComponent(expiry)}&expirations=4`;
const finite = value => typeof value === 'number' && Number.isFinite(value);
const validDate = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(`${value}T00:00:00Z`))
  && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;

function admittedExposure(chain, ticker, expiry, contractsClean) {
  const series = chain?.exposure_by_strike;
  if (!contractsClean || !series || series.series_version !== 'triad-projection.backend.v1'
    || series.formula_version !== 'gex.v2' || series.ticker !== ticker
    || series.fetched_at !== chain.fetched_at || series.spot !== chain.spot
    || !Array.isArray(series.strikes)) return null;
  const seen = new Set();
  for (const row of series.strikes) {
    if (!row || !finite(row.strike) || row.strike <= 0 || seen.has(row.strike)
      || !Array.isArray(row.expiries) || row.expiries.length !== 1 || row.expiries[0] !== expiry
      || !Number.isInteger(row.n_measured) || !Number.isInteger(row.n_total)
      || row.n_total <= 0 || row.n_measured < 0 || row.n_measured > row.n_total
      || row.partial !== (row.n_measured > 0 && row.n_measured < row.n_total)
      || (row.n_measured > 0 ? !finite(row.gex) : row.gex !== null)
      || row.gex_basis !== (row.partial ? 'OI_PARTIAL' : row.n_measured ? 'OI' : 'OI_UNKNOWN')) return null;
    seen.add(row.strike);
  }
  return series;
}

export default function TriadDesk({ ticker }) {
  const [scope, setScope] = useState('0dte');
  const [attempt, setAttempt] = useState(0);
  const requestKey = JSON.stringify([ticker, scope, attempt]);
  const [reading, setReading] = useScopedReading(requestKey);
  const [review, setReview] = useScopedReading(requestKey);
  const [copyStatus, setCopyStatus] = useScopedReading(requestKey);
  const currentKey = useRef(requestKey);
  currentKey.current = requestKey;

  useEffect(() => {
    const ctrl = new AbortController();
    let alive = true;
    let timedOut = false;
    let timer;
    const json = async url => {
      const response = await fetch(url, { signal: ctrl.signal });
      if (!response.ok) throw new Error(`${url.includes('/expiries?') ? 'expiries' : 'chain'} HTTP ${response.status}`);
      const body = await response.json();
      if (ctrl.signal.aborted) throw new Error('Superseded scope');
      return body;
    };
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        timedOut = true;
        reject(new Error('Scope read timed out after 20 seconds.'));
        ctrl.abort();
      }, 20000);
    });
    const load = async () => {
      const listed = await json(expiriesUrl(ticker));
      if (listed?.version !== 'coverage-read.v1' || listed.ticker !== ticker
        || listed.window?.min_dte !== 0 || listed.window?.max_dte !== 7 || !Array.isArray(listed.expiries)) {
        throw new Error('Expiry response does not identify the requested symbol and 0–7 day window.');
      }
      const candidates = listed.expiries.filter(row => row?.admitted === true && validDate(row.expiry)
        && Number.isInteger(row.dte) && row.dte >= 0 && row.dte <= 7
        && (scope === '0dte' ? row.dte === 0 : row.dte > 0))
        .sort((a, b) => a.dte - b.dte || a.expiry.localeCompare(b.expiry));
      const picked = candidates[0];
      if (!picked) return { status: 'empty', note: scope === '0dte'
        ? ticker.startsWith('^') ? 'Index-option entitlement and the actual listed series need verification.'
          : 'No same-day series listed for this symbol in this window.'
        : 'No admitted next-listed expiry within the requested 1–7 day window.' };
      setReading({ status: 'loading-chain', expiry: picked.expiry, dte: picked.dte });
      const body = await json(chainUrl(ticker, picked.expiry));
      if (body?.ok !== true || body.ticker !== ticker || !Array.isArray(body.contracts)
        || !Array.isArray(body.expiries) || body.expiries.some(date => date !== picked.expiry)) {
        throw new Error('Chain response does not identify the requested symbol and expiry.');
      }
      return { status: 'ready', expiry: picked.expiry, dte: picked.dte, chain: body };
    };
    Promise.race([load(), deadline]).then(value => {
      if (alive && !ctrl.signal.aborted) setReading(value);
    }).catch(error => {
      if (alive && (!ctrl.signal.aborted || timedOut)) setReading({ status: 'error', message: error.message || 'Scope read failed.' });
    }).finally(() => clearTimeout(timer));
    return () => { alive = false; clearTimeout(timer); ctrl.abort(); };
  }, [ticker, scope, attempt, setReading]);

  const chain = reading?.status === 'ready' ? reading.chain : null;
  const expiry = reading?.expiry || null;
  const contracts = chain?.contracts || [];
  const admission = useMemo(() => admitContracts(contracts, ticker, expiry), [contracts, ticker, expiry]);
  const series = admittedExposure(chain, ticker, expiry, admission.clean);
  const spot = finite(chain?.spot) ? chain.spot : null;
  const selection = review?.selection || null;
  const selectedRow = review?.osi ? admission.rows.find(row => row.osi === review.osi
    && row.type === review.type && row.strike === selection?.strike) : null;
  const focusStrike = selection => { setReview({ selection }); setCopyStatus(null); };
  const selectContract = row => {
    setReview({ selection: { strike: row.strike, expiry }, osi: row.osi, type: row.type });
    setCopyStatus(null);
  };
  const switchScope = next => { if (next !== scope) setScope(next); };

  const copyTriadContext = async () => {
    const payload = {
      kind: 'triad-context', version: 1, ticker, scope, expiry, selection, spot,
      contract: selectedRow ? { osi: selectedRow.osi, type: selectedRow.type, expiry, strike: selectedRow.strike } : null,
      chain_source: chain?.data_source || null, chain_fetched_at: chain?.fetched_at || null,
      chain_event_time: chain?.event_time || null, chain_stale: chain?.stale ?? null,
      exposure_series_version: series?.series_version || null,
      exposure_coverage: series?.coverage || null, exposure_source_coverage: series?.source_coverage || null,
      note: 'research-only frozen scope; not an execution permission',
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload));
      if (currentKey.current === requestKey) setCopyStatus('Context copied.');
    } catch (_) {
      if (currentKey.current === requestKey) setCopyStatus('Copy failed: clipboard unavailable.');
    }
  };

  return <section className="wall-desk" aria-label="Triad same-day wall desk">
    <div className="context-mini wall-desk-scope">
      <strong>{ticker}</strong><span className="mono">{spot != null ? `Spot ${spot.toFixed(2)}` : 'Spot unknown'}</span>
      <button type="button" aria-pressed={scope === '0dte'} onClick={() => switchScope('0dte')}>0DTE</button>
      <button type="button" aria-pressed={scope === 'next'} onClick={() => switchScope('next')}>Next listed</button>
      <small>{expiry ? `${expiry} · ${reading.dte} DTE · ${reading.status === 'ready' ? 'loaded scope' : 'chain pending'}` : 'no expiry selected'}</small>
    </div>
    <p className="chart-caption">Listed window: 0–7 days · next listed means the earliest admitted future date returned in this window. Listing coverage may be limited.</p>
    {(!reading || reading.status === 'loading-chain') && <p role="status">Loading {reading?.expiry ? `chain for ${ticker} · ${reading.expiry}` : `listed expiries for ${ticker} · ${scope === '0dte' ? '0DTE' : 'next listed'}`}…</p>}
    {reading?.status === 'empty' && <div className="panel wall-desk-empty" role="status">
      <h2>{ticker}: {scope === '0dte' ? 'same-day chain not verified' : 'next-listed chain not verified'}</h2>
      <p>{reading.note}</p>
      {scope === '0dte' && <button type="button" onClick={() => switchScope('next')}>Review next listed expiry</button>}
      <button type="button" onClick={() => setAttempt(n => n + 1)}>Retry scope</button>
      <p>Next listed remains a dated, separate scope.</p>
    </div>}
    {reading?.status === 'error' && <div className="wall-desk-error"><p role="alert">Triad scope unavailable · {reading.message}</p>
      <button type="button" onClick={() => setAttempt(n => n + 1)}>Retry scope</button></div>}
    {chain && <>
      <p className="chart-caption">Source {chain.data_source || 'unknown'} · Receipt {chain.fetched_at || 'unknown'} · chain observation {chain.event_time || 'unknown'} · {chain.stale === true ? 'stale snapshot' : chain.stale === false ? 'producer reports not stale' : 'freshness unknown'}. Quote observations are listed separately.</p>
      <div className="panel exposure"><div className="panelhead"><strong>Exposure by strike</strong>
        <div className="chart-legend"><span>Gold positive · purple negative</span><span>Negative hatched · partial outlined</span><span>Unknown gray</span></div>
      </div>
        {series ? <TriadExposure key={`${ticker}:${expiry}:${chain.fetched_at}`} series={series} spot={spot}
          selectedStrike={selection?.strike ?? null} onSelect={strike => focusStrike({ strike, expiry })} />
          : <p role="status">Admitted exposure unavailable for this chain snapshot. Unambiguous contract rows remain available for review.</p>}
        <div className="chart-caption">Same strike rail · {expiry} · server-admitted exposure; unknown rows are not neutral.
          {series && <> Receipt {series.fetched_at || 'unknown'} · observation {series.event_time || 'unknown'}.</>}
          {series?.source_coverage?.skipped?.length > 0 && <span> Source coverage includes skipped expiries; displayed rows do not prove complete listing coverage.</span>}
        </div>
        <details><summary>Exposure units and formula</summary>
          <p>Conventional signed OI gamma, USD per 1% spot move · gex.v2: Σ sign(type) × Γ × multiplier × spot² × 0.01 × OI; calls positive, puts negative. The backend supplies values and measured coverage. Partial values are observed subtotals, not complete totals. This chart does not infer dealer positions, trade direction, or volume × |delta| behavior.</p>
        </details>
      </div>
      <TriadChainTable rows={contracts} ticker={ticker} expiry={expiry} selectedStrike={selection?.strike ?? null}
        onReview={focusStrike} onSelectContract={selectContract} />
      <aside aria-label="Triad wall review">
        <h3>Wall read</h3><p>{selection ? `Selected ${selection.strike} · ${selection.expiry} · ${ticker}. A selection is a zone focus, not a classified structural wall.` : 'Select a strike to focus review; nothing is selected.'}</p>
        <h3>Selected contract</h3>
        {selectedRow ? <><p>{selectedRow.osi} · {selectedRow.type} · {selectedRow.expiry} · bid {finite(selectedRow.bid) ? selectedRow.bid : 'unknown'} / ask {finite(selectedRow.ask) ? selectedRow.ask : 'unknown'} · exposure {finite(selectedRow.gex) ? `${selectedRow.gex} (${selectedRow.gex_basis || 'basis unknown'})` : 'unknown (not zero)'}</p><ContractClocks row={selectedRow} /></>
          : <p>No contract selected — choose an explicit call or put contract ID in the table.</p>}
        <h3>Entry and protection</h3><p>Entry only after your price confirmation, in whole contracts at broker increments. Exact supported contract plus commissioned policy required; this desk grants neither.</p>
        <h3>Flow context</h3><button type="button" onClick={copyTriadContext}>Copy Triad context</button>{copyStatus && <p role="status">{copyStatus}</p>}
        <h3>Handoff trace</h3><p>{selection ? `Wall context attached · ${ticker} · ${selection.strike} · ${selection.expiry} · chain ${chain.fetched_at || 'time unknown'}` : 'No selection attached.'} Execution owner: unselected — choosing an owner labels a future draft only and never authorizes entry.</p>
      </aside>
    </>}
  </section>;
}
