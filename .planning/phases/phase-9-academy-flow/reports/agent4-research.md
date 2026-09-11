# Agent 4 Research Report (2026-09-03)

## Sources fetched
13 confirmed handoff papers re-verified via SSRN/RePEc/ScienceDirect index pages (all resolve);
prior full verification records in /tmp/wf_smart (paper_informed/gamma/dark.md). Supporting: EOS98,
CCG05, VPIN12, BRW17, NPP05-pinning, Barber-Odean, Barbon EOD WP. Data docs: FINRA ATS, Reg SHO/CRS
R43739, Rule 605/606 (cached); Finnhub/Tradier/yfinance/Databento listed with constraints.

## Sources unavailable
0DTE peer-reviewed literature (gap — Cboe exchange note only, context-grade); intraday signed options
flow; intraday VRP; demand-based pricing full text; Muravyev-family cites (do NOT use names until opened);
BJZZ 2024 reassessment. See missing-literature.md source-request manifest (6 pulls).

## Confirmed rules
Sign-of-gamma amplify/dampen (Ni21); fragile/reversal-lean tags (Barbon-Buraschi, association only);
EOD momentum lean + fade (Baltussen21, GammaHP WP); buyer-open PC + O/S + parity-dev + smirk + IV-change
+ openings-over-closings rules (PP06, JS12, RSS10, CW10, XZZ10, An14, GLP16); dark-as-unsigned (Zhu14,
CFP15); retail scope limit (BJZZ21).

## Refuted violations found (all with file:line in refuted-claims-audit.md)
- V1 (P0): gex_paper_accurate.py flash_crash_risk() returns numeric crash_probability_estimate (1/3/8/18%) —
  paper shows association only.
- V2 (P0): user-facing "VPIN" served from unsigned call/put buckets (routes/vpin.py, services/
  vpin_toxicity.py, routes/quant.py:124-136, routes/ensemble.py). Frontend copy already honest.
- V3 (P1): "Barbon-Buraschi Eq. (2)" + Sec. II.B/III.C/Table V refs unverified (abstract-only source);
  own scaling admitted ~13x off paper scale.
- V4 (P1): Ni dated "(2020)" — journal is RFS 34(4) April 2021.
- Clean: no dark-pool directional copy, no confirmed-buyer copy, no true-sweep claims, no -$200mm line,
  no phantom papers, no guaranteed/will-move in frontend/src.

## Score spec summary
Signed -100..+100, display-only. D2 sign matrix (put-ASK BULLISH + HEDGE?). Weights: spread 25 /
size-OI 30 / premium 20 / IV-change 15 / DTE 10. Caps: OI-missing 50, falling-OI 40, earnings 70.
NO_QUOTE → unavailable. Overfit warning included. 10 unit tests defined; fixtures cover boundaries.

## Dark pool methodology summary
Levels + size only; Top-N 1/2/3/5 × lookback 30/45/90/180d × min-notional × tolerance max(0.25%,10 ticks);
strength = notional + count + recency; freshness per level; confluence checklist; empty + paid-gate states;
5 banned / 6 allowed copy strings; DP $X · date label format.

## Evaluator fixtures created
eval/phase-9/fixtures/: pulse-overview-score.json (5 pulse + overview + 3 highlight + 4 score cases),
scanner-alerts-tracker-filters.json (4 scanner + 6 alerts + tracker + 3 filter cases),
darkpool-context-missing.json (levels + FINRA + SHO + 9 missing-field states). All with expected outputs.

## Recommended product changes
R1 kill numeric crash probability → fragility tag. R2 rename user-facing VPIN → toxicity proxy.
R3 fix Ni year + strip unverified Eq/Sec/Table numbers (Agent 3 B8 patch). R4 copy-grep CI gate.
No contract-request file exists (Agent 1 has not created CONTRACT_REQUESTS.md yet) — R1-R4 logged here
for architect triage.

## Blockers
- CONTRACT_REQUESTS.md absent → requests parked in this report.
- 0DTE/intraday full texts unopened → score DTE weight + 0DTE gate stay heuristic-grade.
- No branch created (repo has concurrent uncommitted work + no git identity assurance for agent branch);
  files written in place, commit left to operator. See output block.

## Round-2 re-verification addendum (same day)

Re-ran all rg audits repo-wide (backend/services, routes, frontend/src, docs) + read Agent-2's new
flowseeker UI + verified 3 citations at index level (Ni RFS 34(4):1952–1986 confirmed;
GPP = RFS 22(10):4259 = 2009 confirmed with NYU PDF pull queued; COR Drift Burst Hypothesis SSRN
2842535 real but price-data-based, misspelled "Reno" in code).
New findings V5–V13 in refuted-claims-audit.md §5 (9 items): OI-PCR misattribution (V5), phantom Ni
charm paper contradicting prior refutation (V6), GPP year shuffle (V7), overnight-drift contradicts fade
finding + vague post-SVB cite (V8), HOW-TO-READ asserts crossing as fact (V9, frontend P0), THREE
conflicting sweep definitions (V10, P0), SIDE fallback makes NO_QUOTE unreachable (V11), WHALE naming
collision (V12, minor), drift-burst gamma→COR misattribution (V13).
Propagation upgrade: V1/V5–V8 all served via morning_briefing API — briefing consumers now in audit scope.
Fixtures added: sweep_definition_conflict, side_fallback, popover_copy evaluator cases.
Claim-rule-map carries P&P OI caveat. What round 2 did NOT do: open GPP PDF, pull 0DTE full texts,
write backend docstring patches (Agent 3 B8 lane) — all queued.

## Rounds 3–5 hardening addendum

- Round 3: V15 (P&P band +4 LIVE in flow_alerts.py:165-167, label :322, 8 wired imports — round-1 "clean"
  verdict corrected), V16 (briefing API serves crash_prob wholesale — CLOSED as served), V14 (split gap),
  V17 (ΓIB double-weight), score-spec reconciliation, runnable check_fixtures.py (caught 3 malformed cases).
- Round 4: V6 upgraded — phantom 'Charming!' + SSRN 5054370 named verbatim (:1005-1007); GPP full text
  fetched (RFS 22(10) 2009, doi 10.1093/rfs/hhp005) with middle-section findings (dealer-short-index,
  crashophobia OTM puts, ~1/3 expensiveness, demand↔smirk); Bollen-Whaley 2004 queued; V19 acceptable-use
  note; all fixture math mechanically recomputed.
- Round 5: Barbon FULL TEXT fetched (UniSG Alexandria OA PDF). V3 → REFUTED-as-cited (imbalance is Eq. 3/4
  not Eq. 2; §II.B is definitions not flip; flash is §IV not §III.C; ~15bps spread is Table VII not V).
  V13 → Table VIII real but code's numbers contradict paper (t=5.99 vs claimed −2.97) + no-causation caveat
  and post-2010 decay omitted. V18 CLOSED as no-violation (matched-pairs confirmed). Claim map carries
  full-text numbers with qualifier requirements. V15 wiring recounted to 8 imports.
- Round 6: audit citation-integrity recheck (all backend lines hold; 3 frontend refs drifted under Agent-2
  edits — V9/V10 line numbers updated, stale refs corrected). Ni 2006 WP full text verified (mechanism +
  no-formula at source, ±37bp per 1σ). Score-spec EXECUTED against all 10 unit tests — caught and fixed
  2 spec bugs (IV now direction-aware; MID halving now in pseudocode). New V10 sub-finding: :1351 tooltip
  "urgent multi-exchange fill" asserts venue visibility; "(heuristic)" only partly mitigates.
- Round 7: fix-queue F1–F18; Cboe 0DTE full text (net-vs-gross supports gate philosophy); venue-noun ban.
- Round 8: §1 verdict-table corrected (P&P row now VIOLATION per V15; ΓIB row now REFUTED-as-cited per
  full text). Baltussen abstract verified verbatim + DOI. Fixture inventory re-checked (all keys present,
  checker PASS).
- Round 9: first verified 0DTE paper (Brogaard-Han-Won 2023/2026, abstract-only — PDF SSRN-walled):
  +1σ 0DTE → +9.1% vol, survives gamma controls, retail-driven — CONTRADICTS Cboe de-minimis; honest
  position is "mixed, SPX-only, regime-dependent". Checklist gains fragility-qualifier rule.
- Round 10: BJZZ abstract verified verbatim (10bp/wk, <half persistence, suggestive-only) — claim-map
  numbers now sourced, not remembered.
- Round 11: 5 more abstracts verified verbatim (Zhu, CFP+DOI, CW-51bp, XZZ-10.9%, An — caught own
  decile/quintile error); phantom §1 row corrected (Charming! variant present per V6).
- Round 12 (/loop): backend :8000 unreachable from agent shell (timeouts) — live API confirmation of V16
  blocked without restarting another lane's server; NOT attempted. Code-level propagation stands.
  Audited Agent-2 W2 fingerprints (973bbb3): honest, added to clean list. New F19 (P2): "negotiated
  single fill" block tooltip.
- Round 13 (/loop): recovered dangling round-11 commit f554e4f (branch moved under agent) via checkout of
  own lane files. New V20 (P1): FIR divergence — contract (agent1 branch) defines call-put FIR, shipped
  overviewStats computes signal-side FIR; same name/threshold, different quantity. BRANCH RISK (P1
  process): Agent-1 planning (CONTRACTS 1305 lines, CONTRACT_REQUESTS 611 lines) unmerged on
  phase9/agent1-architect; Agent-4 lane split across main + dangling commit; CONTRACT_REQUESTS has NO
  Agent-4 triage — F1–F19+R1–R4 still parked in agent4 report. Agent 1 must reconcile at merge.

## Agent 4 status block (per task prompt)

AGENT: 4
BRANCH: main (scoped lane-only commits; other lanes' work untouched)
STATUS: DONE
SOURCES_FETCHED: 13/13 handoff + EOS98/CCG05/VPIN12/BRW17/NPP05/Barber-Odean/Barbon-EOD-WP/GPP-full-text/Ni-WP/Cboe-0DTE/Baltussen-abstract/BJZZ-abstract/Brogaard-abstract
SOURCES_UNAVAILABLE: peer-reviewed 0DTE full texts; intraday signed-flow; intraday VRP; Bollen-Whaley 2004; BJZZ-2024 reassessment (manifest in missing-literature.md)
VIOLATIONS_FOUND: V1–V19 + V6-upgrade + V13/V3 full-text verdicts (audit §§1–6); fix queue F1–F18 (fix-queue.md)
EVALUATORS_CREATED: 3 fixture JSONs (40+ cases) + check_fixtures.py (PASS)
SCORE_SPEC: signed-score-spec.md incl. executed 10-test proof run
DARK_POOL_SPEC: dark-pool-methodology.md (levels+size only, Top-N×lookback, banned/allowed copy)
BLOCKERS: CONTRACT_REQUESTS.md absent (R1–R4 + F1–F18 parked for Agent 1); product edits are owner lanes
