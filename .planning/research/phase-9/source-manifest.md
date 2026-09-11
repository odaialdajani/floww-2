# Phase 9 Source Manifest — Agent 4

**Created:** 2026-09-03 · **Agent:** 4 · **Branch:** see report
**Method:** SSRN/RePEc/ScienceDirect abstract pages + author PDFs opened in prior verification passes
(artefacts in /tmp/wf_smart/: paper_informed.md, paper_gamma.md, paper_dark.md).
Web re-check 2026-09-03 confirmed index pages still resolve for starred items.

**Status legend:** fetched = full abstract + record opened · cached = prior-pass record in /tmp/wf_smart
· abstract-only = abstract opened, full text paywalled · unavailable = not found / not attempted.

## 1. Confirmed papers (from handoff §4)

| # | Paper | Status | Link |
|---|---|---|---|
| 1 | Pan & Poteshman 2006, RFS 19(3):871–908 (NBER w10925) | fetched+cached | https://ssrn.com/abstract=622869 |
| 2 | Johnson & So 2012, JFE 106(2):262–286 | fetched+cached | https://ssrn.com/abstract=1624062 |
| 3 | Roll, Schwartz & Subrahmanyam 2010, JFE 96(1):1–17 | fetched+cached | https://ssrn.com/abstract=1410091 |
| 4 | Cremers & Weinbaum 2010, JFQA 45(2):335–367 | fetched+cached | https://ssrn.com/abstract=968237 |
| 5 | Xing, Zhang & Zhao 2010, JFQA 45(3):641–662 | fetched+cached | https://ssrn.com/abstract=1107464 |
| 6 | An, Ang, Bali & Cakici 2014, JF 69(1):227–275 | fetched+cached | https://ssrn.com/abstract=1533089 |
| 7 | Ge, Lin & Pearson 2016, JFE 121(1):260–286 | fetched+cached | https://ssrn.com/abstract=2329714 |
| 8 | Ni, Pearson, Poteshman & White 2021, RFS 34(4):1952–1986 (SSRN 2867461; NOTE: journal year is 2021, not 2020) | fetched+cached | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2867461 |
| 9 | Barbon & Buraschi, "Gamma Fragility", SSRN 3725454 (2020/2021) | FETCHED FULL TEXT round 5 (UniSG Alexandria open-access PDF, 2020/05) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454 |
| 10 | Baltussen, Da, Lammers & Martens 2021, JFE 142(1):377–403 (SSRN 3760365) | fetched+cached | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3760365 |
| 11 | Boehmer, Jones, Zhang & Zhang 2021, JF 76(5):2249–2305 | fetched+cached | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2822105 |
| 12 | Zhu 2014, RFS 27(3):747–789 | fetched+cached | https://ideas.repec.org/a/oup/rfinst/v27y2014i3p747-789..html |
| 13 | Comerton-Forde & Putnins 2015, JFE 118(1):70–92 | fetched+cached | https://ideas.repec.org/a/eee/jfinec/v118y2015i1p70-92.html |

Supporting (verified in prior passes, usable for rules):
- Easley, O'Hara & Srinivas 1998, JF 53(2) — abstract-only+cached — https://ssrn.com/abstract=98724
- Cao, Chen & Griffin 2005, JB 78(3) — abstract-only+cached — https://ssrn.com/abstract=445320
- Easley, Lopez de Prado & O'Hara 2012 (VPIN), RFS 25(5) — abstract-only+cached — https://ssrn.com/abstract=1695596
- Buti, Rindi & Werner 2017, JFE 124(2) — abstract-only+cached — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1630499
- Ni, Pearson & Poteshman 2005 (expiry pinning), JFE 78(1) — abstract-only+cached — https://ssrn.com/abstract=519044
- Barber & Odean 2000, JF 55(2) / 2011 survey — abstract-only+cached
- Barbon et al. EOD rebalancing WP (ΓHP) — PDF opened in prior pass+cached

## 2. Missing 0DTE / intraday literature targets

See missing-literature.md. Status mostly abstract-only (new search 2026-09-03, index pages resolve;
full texts not all opened — do not cite beyond abstract until opened).

## 3. Public GitHub pattern targets

See github-patterns.md. Patterns only, no code copied. All statuses: listed (not cloned), licenses recorded.

## 4. Data-source docs

| Source | Doc | Status |
|---|---|---|
| Finnhub calendar (free, 1-mo history) | https://finnhub.io/docs/api/calendar-earnings | listed — not re-fetched this pass; constraint per HANDOFF §5 |
| FINRA ATS/OTC transparency (weekly, delayed, no side) | https://www.finra.org/filing-reporting/otc-transparency | cached (prior pass) |
| Reg SHO daily | FINRA Reg SHO + CRS R43739 https://www.congress.gov/crs-product/R43739 | cached (prior pass) |
| Tradier (sandbox delayed, no greeks) | https://documentation.tradier.com/ | listed — constraint per HANDOFF §5 |
| yfinance (chain snapshots) | https://github.com/ranaroussi/yfinance (Apache-2.0) | listed |
| Databento (backtest harness candidate) | https://databento.com/docs | listed |
| SEC Rule 605/606 | https://www.sec.gov/files/rules/proposed/2022/34-96493.pdf | cached (prior pass) |
