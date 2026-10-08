# Integration audit — merged head `f1e76e82` (2026-10-08, read-only)

Question: is everything well connected at the merged head? Checked by
reading exact merged source (`git show f1e76e82:...`), no checkouts edited.

## 1. TriadDesk data contracts match the backend

- Expiries: desk sends `min_dte=0&max_dte=7&expirations=12` → route allows
  `min_dte ge=0`, `expirations` 1–16, returns `range_map.admitted_expiries`.
  The desk's Next-listed repair reads exactly that key. MATCH.
- Chain: desk sends `expiration=&expirations=4` → route accepts both
  (`expirations` 1–12), returns annotated `contracts` (with per-row `gex`
  + basis), `spot`, `data_source`. The desk reads exactly those keys;
  `fetched_at` degrades to "time unknown" if absent. MATCH.
- Exposure render consumes per-row `gex`/`gex_basis` from
  `annotate_contract_exposure` — the same annotation the backend tests pin.
  No invented metric crosses the wire. MATCH.

## 2. App mount is isolated, bounded, and order-free

- Mount: `page === "trinity"` + `trinityTab === "desk"` sub-tab, under an
  `ErrorBoundary`; default tab keeps the existing TrinityView, so the
  current Market view still loads first. OPT-IN, existing views preserved.
- Props: `<TriadDesk ticker={ticker} />` only. Sibling `TrinityView`
  (`onTradeSelect`) and `QuickTradePanel` (`onSubmit`) carry the legacy
  trade handlers — the desk is wired to NEITHER (prop-level proof) and its
  file references no order API. The desk cannot submit by construction.
- `^`-prefixed tickers (SPX) flow to the desk unchanged, where they hit
  the pinned entitlement message instead of a series. Covered by test.

## 3. Cline slices vs consumers

- U13 middleware: no route/signature change — pure budget accounting;
  downstream auth/capture gates still run (`call_next`). No consumer impact.
- U12 trinity shape: only consumer (`BriefingStrip`) is null-safe and
  renders the new interpretation strings; `TrinityView` never reads the
  reshaped fields. No frontend change required.
- U02 null-date: producer emits `oi_dates or None` with "absent means
  unknown" — the admitted `null` mirrors a real shape. MATCH.

## 4. Lane parity

`host-opencode` vs `host-cline` frontend trees identical except my
`unified-tests/` additions. No cross-lane writes by either side observed.
Cline backend work (`server.py`, `trinity.py`) is uncommitted in its lane,
undeployed; previews still serve pre-slice code.

## Verdict

Integrated and consistent at `f1e76e82`. Remaining openings are all
known and owned elsewhere: Cline post-merge review (T03), U06–U08/U10–U11/
U15–U16/C17 (Cline), redeploy for the 429 fix (needs human authorization),
commissioning (Nav).
