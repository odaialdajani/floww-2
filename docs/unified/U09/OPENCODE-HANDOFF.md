# Handoff — confusing bare-phrase navigation (OpenCode → Coordinator, 2026-10-08)

File: `frontend/src/agent/chatNavigation.js` (`parseChatNavigation`).
Counterexample: `show me the stock chart` resolves to
`{page: 'heatseeker', ticker: 'STOCK'}` — the `chart` key's
before-regex binds the word "stock" as a ticker. Downstream
`verifyNavigationTicker` then fails it ("not in the provider's available
stock list"), so a plain navigation request ends in a confusing
not-a-stock error instead of opening the chart.

Smallest correction sketch (NOT applied — out of my U09 selectors, needs
coordinator scoping): check exact multi-word target names before single-key
prefix/suffix ticker bindings, or drop pseudo-ticker bindings that fail an
all-letters common-word screen. Pinned current behavior in
`frontend/src/unified-tests/context-generation.test.jsx`
("ticker-qualified navigation never invents grounding") so any fix must
update that pin deliberately.

No duplicate: no existing issue/probe covers this phrase path
(`chatNavigation.test.js` cases are all-null paths).
