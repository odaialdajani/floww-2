# Independent sample-chain restoration review - 2026-09-26 22:30 UTC

PASS for the four sample-fixture skips only. No blocking finding. This does not close the other35skips, certify production financial models, or substitute demonstration data for observed market evidence.

## Provenance and original-byte verification

Read only the pinned raw GitHub resources at FlashAlpha-lab/gex-explained commit a11321d62006311c4a72a68552587485024f2bf2. Both packaged files equal upstream byte-for-byte: data/sample_chain.csv is1172bytes and LICENSE is1071bytes. SHA256 values match PROVENANCE.md and are recorded below. The complete upstream MIT notice including copyright2026 FlashAlpha Lab remains beside the sample.

URLs independently fetched:
- https://raw.githubusercontent.com/FlashAlpha-lab/gex-explained/a11321d62006311c4a72a68552587485024f2bf2/data/sample_chain.csv
- https://raw.githubusercontent.com/FlashAlpha-lab/gex-explained/a11321d62006311c4a72a68552587485024f2bf2/LICENSE

## Executed narrow evidence

Python3.11.15 independently ran only backend/tests/test_analytics_vex_dex_vega.py using --noconftest --import-mode=importlib -p tests.offline_network -o addopts=, with DUCKDB_PATH=:memory:. Result29passed,0skipped,0.82s, one unrelated Hypothesis directory-collection warning. No app startup, provider/model call or production data write. Python launched through Node spawnSync windowsHide:true.

Additional direct assertions passed:25contracts,13unique strikes, spot590, every T=30/365; every modeled IV equals the preserved original moneyness formula. All returned numerical values from all three sample calculators are finite. Totals: VEX=-12210793.7, DEX=933227503.41, Vega=10314594.54, summed contract OI=167230. These are deterministic demonstration calculations, not claimed market observations.

Date-independence was checked with the loader's datetime.now/today replaced by functions that raise: default valuation still loads and calculates. Explicit valuation2026-03-21 is rejected because it does not precede expiry. A deliberately missing, never-created sibling fixture path raises FileNotFoundError; it cannot silently skip. No fixture bytes were changed for these checks.

## Source review and claim boundary

Packaged path is resolved relative to the test file. Runtime current-date fallback and external workspace sample path are removed. Fixed2026-02-19valuation is30calendar days before2026-03-21expiry, explicitly modeled, with original volatility assumption retained. PROVENANCE.md explicitly identifies the upstream demonstration sample as neither FLOWW-generated replacement nor verified historical market capture. It also distinguishes modeled valuation/volatility from source observation and executable prices. This is a sound restoration of four missing-fixture checks and does not upgrade synthetic/demo evidence to real market acceptance.

## Checked SHA256

- backend/tests/test_analytics_vex_dex_vega.py: 4947ebce321c81b085cec039266b3572cdc7b0d4e916f4fab9cfabbfec0af0ac
- backend/tests/fixtures/flashalpha_gex/sample_chain.csv: 6e1e6617916580ae60ff9d5e6327f16e1da36992744fa8e29ba98364918d4b54
- backend/tests/fixtures/flashalpha_gex/LICENSE: f74471056c5088727be5fb5a638db72f1f9612134d4a09e91718fe3b2b536e1c
- backend/tests/fixtures/flashalpha_gex/PROVENANCE.md: 7e79701412b4efd80cf949a61a10f5209f5ca24fda4af03b2045de004e184b4d

## Final small-delta closure - 22:31 UTC

Independently reran the same targeted29tests after CSV hash assertion and byte-preserving attributes were added:29passed,0skipped (one existing Hypothesis warning). All six hashes below remained unchanged across that final run. Source review confirms assertion pins the CSV to its independently verified upstream SHA256. git check-attr reports text:unset for both original files, preventing text line-ending conversion. Pre-existing qc/data/flashalpha_sample_chain_manifest.json recorded1172bytes/25rows and identical CSV hash on2026-05-18; this separately confirms restoration of the original previously ingested demonstration fixture. Provenance now records that continuity without upgrading it to a verified historical capture.

- backend/tests/test_analytics_vex_dex_vega.py: 96a60d8e67e5c5a6c977348ad7ac291e3ff672d5facc7fd27e56fb5fe500ef7d
- backend/tests/fixtures/flashalpha_gex/sample_chain.csv: 6e1e6617916580ae60ff9d5e6327f16e1da36992744fa8e29ba98364918d4b54
- backend/tests/fixtures/flashalpha_gex/LICENSE: f74471056c5088727be5fb5a638db72f1f9612134d4a09e91718fe3b2b536e1c
- backend/tests/fixtures/flashalpha_gex/PROVENANCE.md: 254bbb83f86078ba2d44319a8b80ec822c4713103d98bfef909e10e91439d7ad
- .gitattributes: a6affcffbeaac1d89f0b7f46dcdc5762dcd8302ffea233b409060f828d13e494
- qc/data/flashalpha_sample_chain_manifest.json: 668abe7aa248aef0e7fefc0cefb00f269b3968e52caf41bffe68297fb523af69
