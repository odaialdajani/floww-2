/**
 * NewsBadge.jsx — Solstice Row 4 (3rd-column) news pulse tile.
 *
 * Fetches GET /api/news/{ticker}/history?days={N} (default days=14) and surfaces
 * 5 fields the steal-list .md explicitly lists for Flowseeker alert correlation:
 *
 *   1. n_headlines_last_24h  — int  ; total headlines within the most-recent 24h
 *   2. n_unique_domains       — int  ; breadth of publisher coverage (signal: more
 *                                       domains = more institutional attention)
 *   3. top_3_publishers       — list[str] of publisher hostnames; rendered as
 *                                 single-letter monogram chips (R = reuters.com, etc.)
 *   4. catalyst_news          — bool ; true if a 14d-window headline tagged as
 *                                 catalyst (FOMC / earnings / M&A / guidance)
 *   5. latest_headline_ts     — ISO datetime string; rendered as relative time
 *
 * Defensive degrade mirrors StrikeConeBadge / OpportunityBadge:
 *   - Loading     → animate-pulse skeleton (5 placeholder bars)
 *   - Backend err → amber card "Catalyst Pulse · offline"
 *   - Empty data  → slate card "No news in 14d window"
 *   - 2xx body    → success card with the 5-field tile grid
 *
 * Polls every 5 minutes (matches news-feed freshness cadence; backend writes
 * to floww.news_headlines_daily in news_feed.py).
 *
 * Audit: docs/reports/2026-07-11-steal-list-integration-roadmap.md (news
 * feed entry in the steal-list #6/#9/#10/#20 row).
 */

import React, { memo, useEffect, useState } from "react";
import { BACKEND_BASE } from "../../config/api";
import { fetchStudyJSON } from "./studyFetch";
import StudyErrorCard from "./StudyErrorCard";

const SIDE_BASE =
    process.env.REACT_APP_STEAL_THREE_BASE || BACKEND_BASE;

/**
 * Convert an ISO datetime string to a compact relative-time tag
 * ("3h", "12h", "2d"). Pure-stdlib — no moment/luxon. Returns "—" for
 * null/invalid inputs so the tile never breaks.
 */
function toRelTime(iso) {
    if (!iso || typeof iso !== "string") return "—";
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return "—";
    const hr = Math.max(0, Math.floor((Date.now() - t) / 3_600_000));
    if (hr < 24) return `${hr}h`;
    const d = Math.floor(hr / 24);
    if (d < 30) return `${d}d`;
    const mo = Math.floor(d / 30);
    return `${mo}mo`;
}

/**
 * First-character monogram of a publisher hostname so the chip is
 * compact. "reuters.com" → "R", "www.bloomberg.com" → "B".
 */
function monogram(host) {
    if (!host || typeof host !== "string") return "?";
    const cleaned = host.replace(/^www\./, "").trim();
    return (cleaned[0] || "?").toUpperCase();
}

function NewsBadge({ ticker = "SPY", days = 14 }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);

    useEffect(() => {
        let cancelled = false;
        const fetchNews = async () => {
            try {
                const url =
                    `${SIDE_BASE}/api/news/${encodeURIComponent(ticker)}` +
                    `/history?days=${days}`;
                const j = await fetchStudyJSON(url);
                if (!cancelled) {
                    setData(j);
                    setErr(null);
                }
            } catch (e) {
                if (!cancelled) {
                    setErr(e);
                }
            }
        };
        setData(null);
        setErr(null);
        fetchNews();
        const id = setInterval(fetchNews, 5 * 60 * 1000);   // 5 min poll
        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, [ticker, days]);

    // ── Defensive degrade: offline ─────────────────────────────────
    if (err) {
        return (
            <StudyErrorCard
                title="Catalyst Pulse"
                base={SIDE_BASE}
                error={err}
                testId="hs-news"
                className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 h-full flex flex-col justify-center"
                footer={<div className="text-[9px] text-slate-500 mt-2">
                    {ticker} · {days}d window
                </div>}
            />
        );
    }

    // ── Defensive degrade: loading ─────────────────────────────────
    if (!data) {
        return (
            <div
                className="rounded-xl border border-slate-700/30 bg-slate-900/40 animate-pulse p-3 h-full flex flex-col"
                data-testid="hs-news"
            >
                <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-2">
                    Catalyst Pulse · {ticker}
                </div>
                <div className="space-y-2 flex-grow">
                    <div className="h-4 bg-slate-800/60 rounded w-full" />
                    <div className="h-4 bg-slate-800/60 rounded w-2/3" />
                    <div className="h-4 bg-slate-800/60 rounded w-3/4" />
                    <div className="h-4 bg-slate-800/60 rounded w-1/2" />
                    <div className="h-4 bg-slate-800/60 rounded w-5/6" />
                </div>
            </div>
        );
    }

    // ── Success path ───────────────────────────────────────────────
    const isCat = Boolean(data.catalyst_news);
    const nHeadlines = Number(data.n_headlines_last_24h) || 0;
    const nDomains = Number(data.n_unique_domains) || 0;
    const pubs = Array.isArray(data.top_3_publishers)
        ? data.top_3_publishers.slice(0, 3)
        : [];
    const relTs = toRelTime(data.latest_headline_ts);

    // Empty data case — clean slate card rather than zero-everywhere tile.
    if (nHeadlines === 0 && nDomains === 0 && pubs.length === 0) {
        return (
            <div
                className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3 h-full flex flex-col justify-center"
                data-testid="hs-news"
            >
                <div className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-1">
                    Catalyst Pulse · {ticker}
                </div>
                <div className="text-[10px] text-slate-500">
                    No news in {days}d window.
                </div>
                <div className="text-[9px] text-slate-600 mt-1">
                    latest activity: {relTs}
                </div>
            </div>
        );
    }

    return (
        <div
            className="rounded-xl border border-slate-700/30 bg-slate-900/40 p-3 h-full flex flex-col"
            data-testid="hs-news"
        >
            {/* Header row */}
            <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                    <span
                        className={`w-1.5 h-1.5 rounded-full ${
                            isCat
                                ? "bg-emerald-400 animate-pulse"
                                : "bg-slate-500"
                        }`}
                    />
                    <span className="text-[10px] uppercase tracking-widest font-bold text-slate-200">
                        Catalyst Pulse · {ticker}
                    </span>
                </div>
                <span className="text-[9px] uppercase tracking-widest font-mono text-slate-500">
                    {days}d window
                </span>
            </div>

            {/* 5-field tile grid
                 Row 1: n_headlines_last_24h (sky) + catalyst_news (emerald/slate)
                 Row 2: n_unique_domains (slate) + latest_headline_ts (teal)
                 Row 3: top_3_publishers monogram chips (slate, full-width) */}
            <div className="grid grid-cols-2 gap-2 flex-grow">
                <div className="bg-sky-500/10 border border-sky-500/20 rounded-md p-2 flex flex-col justify-center items-center">
                    <div className="text-[9px] text-sky-400/70 uppercase tracking-wider">
                        Headlines 24h
                    </div>
                    <div className="text-lg font-bold text-sky-300 leading-tight">
                        {nHeadlines}
                    </div>
                </div>

                <div
                    className={`border rounded-md p-2 flex flex-col justify-center items-center ${
                        isCat
                            ? "bg-emerald-500/10 border-emerald-500/20"
                            : "bg-slate-800/50 border-slate-700/50"
                    }`}
                >
                    <div
                        className={`text-[9px] uppercase font-bold tracking-wider ${
                            isCat ? "text-emerald-400" : "text-slate-500"
                        }`}
                    >
                        {isCat ? "✓ Catalyst" : "✗ No catalyst"}
                    </div>
                    <div className="text-[9px] text-slate-500 mt-0.5">
                        14d scan
                    </div>
                </div>

                <div className="bg-slate-800/40 border border-slate-700/40 rounded-md p-2 flex flex-col justify-center items-center">
                    <div className="text-[9px] text-slate-400 uppercase tracking-wider">
                        Unique Domains
                    </div>
                    <div className="text-base font-bold text-slate-200 leading-tight">
                        {nDomains}
                    </div>
                </div>

                <div className="bg-teal-500/10 border border-teal-500/20 rounded-md p-2 flex flex-col justify-center items-center">
                    <div className="text-[9px] text-teal-400/70 uppercase tracking-wider">
                        Latest
                    </div>
                    <div className="text-base font-bold text-teal-300 leading-tight font-mono">
                        {relTs}
                    </div>
                </div>

                <div className="col-span-2 bg-slate-800/40 border border-slate-700/40 rounded-md p-2 flex items-center justify-between">
                    <div className="text-[9px] text-slate-400 uppercase tracking-wider">
                        Top publishers
                    </div>
                    <div className="flex gap-1.5">
                        {pubs.length ? (
                            pubs.map((p, i) => (
                                <span
                                    key={`${p}-${i}`}
                                    className="w-5 h-5 rounded bg-slate-700/60 border border-slate-600/50 text-[10px] text-slate-200 font-mono font-bold flex items-center justify-center"
                                    title={p}
                                >
                                    {monogram(p)}
                                </span>
                            ))
                        ) : (
                            <span className="text-[9px] text-slate-500">
                                —
                            </span>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default memo(NewsBadge);
