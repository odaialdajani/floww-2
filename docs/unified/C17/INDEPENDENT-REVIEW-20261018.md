# C17 independent review — 18 October 2026

**Verdict: PASS — independent engineering countersign of the original C17 acceptance at `36190e8a2828a4bbdafa9dc45c056162f2faec18`.**

Reviewer: Codex independent read-only agent `chart_roadmap_reconcile`. This reviewer did not author the C17 producer/consumer. Root requested the review; OpenCode remains release owner. No product or original-ledger edits were made. The original row is still stored as PENDING until the integration owner attaches this receipt through its normal acceptance process.

## Exact original criterion

Source: `.planning/eval/completion-20261016/original-obligations.json`, row `C17`, title **Admitted exposure metric for Triad overlay (optional)**, owner Cline, priority P2:

> A backend-admitted per-strike exposure series (measured-vs-unknown basis flags, quarantine rules) versioned into the envelope or a documented endpoint; consumer overlay renders it with honest unknown states; no frontend-invented analytics.

The separate original `observed` field mentions the earlier absence of a raw-versus-adjusted pair. It is historical gap context, not substituted here for the exact acceptance sentence. This review accepts the admitted canonical per-strike series; it does not claim a new adjusted formula, qualified share-volume store, dealer positioning or trading edge.

## Clause-by-clause evidence

| Original clause | Current source and checked behavior | Result |
|---|---|---|
| Backend-admitted per-strike series | `backend/services/triad_projection.py:96` `annotate_contract_exposure` derives contributions through canonical `compute_raw_oi`, including canonical multiplier/quarantine admission. Per-strike aggregation at :266–320 preserves exact fractional strike identity, observed subtotal, measured/total counts, partial flags and missing-reason counts. `exposure_by_strike` at :374 exposes those fields rather than a frontend calculation. | PASS |
| Measured versus unknown basis flags and quarantine | Fresh isolated tests prove partial1/2 is explicit, all-unknown remains null, measured zero remains0 with complete2/2 counts, unknown-side rows stay in the denominator, and an adjusted/quarantined zero remains unknown with `CONTRACT_QUARANTINED`. Source emits `OI`, `OI_PARTIAL`, `OI_UNKNOWN`, counts and reasons. | PASS |
| Versioned envelope or documented endpoint | `backend/routes/public_api.py:77` provides documented read-only `GET /api/public/chain/{ticker}/exposure-by-strike`; :145–160 also embeds the series in the same `/chain/{ticker}` response **from raw input before table-only filtering**. Source carries `triad-projection.backend.v1`, `gex.v2`, original source clocks and skipped-expiry coverage. Router is mounted at `backend/server.py:3854`. Route tests fake the provider and verify exact response, denominator preservation and no order routes. `docs/unified/C17/DEFERRAL.md` documents the endpoint and earlier closure correction. | PASS |
| Consumer overlay renders honest unknown states | Product mounts `TriadDesk` on Market view's **Wall Desk** subtab at `frontend/src/App.js:736`. `TriadDesk.jsx:23` `admittedExposure` validates version, formula, ticker, same fetched-at/spot, per-row selected expiry, finite strike, counts, partial flag and basis; invalid/missing series yields an unavailable notice rather than chain-row fallback (:175–181). `TriadExposure.jsx` draws known zero, gray unknown slots, partial outlines and measured/total labels. Existing paired consumer test pins202500 from admitted fixture despite conflicting contract-row999999; rejects missing/version/ticker/receipt/expiry defects and distinguishes zero from unknown. | PASS |
| No frontend-invented analytics | `TriadExposure` consumes `row.gex`, `n_measured`, `n_total`, `partial` directly. Its calculations choose visible strikes, chart scale, pixel geometry and colors, not exposure. TriadDesk's only admitted overlay input is the same-response backend series. Paired producer/consumer fixture prevents accepting a browser recomputation. | PASS |

## Verification performed and reused

**Fresh reviewer check:** one isolated C17 test module, run from primary `backend/` using its local interpreter:

```text
env FLOWW_MARKET_DATA_PROVIDER=legacy PUBLIC_API_KEY= DB_NAME=floww_c17_review_test .venv/bin/python -m pytest tests/unified/test_exposure_by_strike.py -q --tb=short -p no:cacheprovider --disable-warnings
........... [100%]
11 passed, 31 warnings in 0.25s
exit_code=0
```

These are deterministic synthetic producer/projection/paired-fixture/route checks. The route cases replace the provider with an async fake and mount a minimal FastAPI router; no live provider, model, broker/account, capture or order calls were used. No broad backend or frontend suite was repeated.

**Existing consumer execution receipt:** root's `work/ui-final-gates-20261018.json` records frontend exit0 with unchanged source fingerprint `51ee3bf52648eb8cb5b629a9eff60c05411d9d8cd68999ac44852a026eec6b9b`; `work/ui-final-frontend-20261018.log:283` reports `PASS src/components/triad/TriadDesk.test.jsx`, and :1495–1496 reports210 suites /2342 tests passed. This is reused execution evidence, not rerun by this reviewer. All C17 files below are byte-identical between primary main, its exact Git objects and the UI candidate lane; the uncommitted UI presentation changes do not alter them.

## Binding file identities

| File at reviewed SHA | SHA256 |
|---|---|
| `backend/services/triad_projection.py` | `23b3afdbc94c01f9bea33706d4f2bc84ffc396da0f4f3d2b76dd3206a69b33e1` |
| `backend/routes/public_api.py` | `cc54bb1deb79a8feb76e4a000c3012e33affafb50a5d98f73433f1796679fa3b` |
| `backend/tests/unified/test_exposure_by_strike.py` | `20f2a214cf29fcd95b600a28f242f21698066b711be48fdfe2d6d966066db6b9` |
| `frontend/src/components/triad/TriadDesk.jsx` | `cc114c3fe6efd8efb9cea5a0f0bc9c2fde05bb1e662597276aa86b4a26ab34e3` |
| `frontend/src/components/triad/TriadExposure.jsx` | `dda316c88a3dae0a2314c07d68e1d3d337fbb213d68d97b904a3529287cb146b` |
| `frontend/src/components/triad/TriadDesk.test.jsx` | `014d6f8772f1ac3a87165bfb4fa23f120ff06a4e63417d0d4b8c9d9d6c525843` |
| `frontend/src/test-fixtures/triad-exposure.paired.json` | `58ae605fbe6bb32de0f8f12aafa74cd438bc5d1d874abca620c4a0229f2a527a` |

## Limits and disposition

All clauses of the exact C17 engineering acceptance are met by current source plus fresh producer/route checks and the existing source-matched paired consumer execution receipt. **No unmet C17 clause found.** This countersign is scoped to C17 and its admitted series, not the entire 29-block chart roadmap or the default Market view raw/adjusted heatmap workflow.

The old DEFERRAL text's initial six-test count and sibling FROZEN-SNAPSHOT reference are stale documentation context; current test module has11 tests and the sibling snapshot file is absent. Neither is used as proof here: the exact current SHA, hashes, behavior and real test exit above are binding.

Original NAV account, capture, model, native, visual, release and paper-exemption decisions remain separate. Live freshness/full-market completeness, visual owner acceptance, profit, historical recovery and trading commissioning are not established by this receipt. Screener, stores, services, capture/trading settings and publication were untouched.
