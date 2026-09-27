# Original calculation sample restored - 2026-09-26

Four skipped checks now execute against the exact original FlashAlpha demonstration CSV. This closes that missing-fixture prerequisite only; the other historical skips and the full AI/UI goal remain open.

The original upstream [sample](https://github.com/FlashAlpha-lab/gex-explained/blob/a11321d62006311c4a72a68552587485024f2bf2/data/sample_chain.csv) and its MIT licence are pinned and included under backend/tests/fixtures/flashalpha_gex. The CSV hash 6e1e6617916580ae60ff9d5e6327f16e1da36992744fa8e29ba98364918d4b54,25rows and1172bytes exactly match the already-committed May18qc manifest. No substitute market data was invented. A fixed modeled valuation date2026-02-19 makes the sample's time-to-expiry reproducible; its volatility assumption remains explicitly test-only. Missing/changed fixture bytes now fail instead of skipping. Production calculations are unchanged.

Python3.11.15 actual focused command: backend/.venv/Scripts/python.exe -m pytest tests/test_analytics_vex_dex_vega.py -q --disable-warnings -p tests.offline_network, working directory backend.

Before:25passed,4skipped,27warnings,.73seconds. After:29passed,0skipped,27warnings,.85seconds. Ruff check of the changed test file passes. Root logs are output/sample-chain-before.log and output/sample-chain-final.log. Outbound provider calls were blocked during tests; only pinned GitHub source/licence reads occurred during preparation.

The [independent review](sample-chain-restoration-review-20260926.md) separately checks upstream bytes, original manifest identity, fixture shape, clock independence and test execution. Git attributes keep CSV/licence bytes unchanged on Windows. No full backend rerun is claimed for this fixture-only change; the earlier5946pass/39skip result remains a dated report, not an updated count.
