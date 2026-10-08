# U12 — Cline: Trinity ADV + spillover honesty repair (READY → REVIEW_PENDING request)

Owner: Cline. Baseline `8194eca43a580121901516b291c1b2435da7ce2c`, worktree
`work/host-cline` (uncommitted). Reviewer: OpenCode. Write paths touched:
`backend/routes/trinity.py`, `backend/tests/unified/test_trinity_provenance.py`
(new), `docs/unified/U12/`.

## Counterexamples reproduced (failed-first, injected facts, zero upstream calls)

File `backend/tests/unified/test_trinity_provenance.py`, run RED against
baseline source first (`../evidence/u12-red.log`, sha256 see below; exit 1,
4 failed):

1. **Constant ADV**: `compute_gamma_imbalance(net_gex, spot, adv_shares=75_000_000)`
   served one fixed 75M share ADV to every ticker (`routes/trinity.py:128`).
2. **Self-substituted spillover**: `cross_asset_gamma_spillover(spx=…gib_pct,
   single_stock=…gib_pct)` passed the selected ticker's own gamma imbalance as
   the SPX input — no separate SPX measurement existed.
3. **Silent constituent failure**: `except Exception: pass` made any metric
   failure vanish with no status at all.

## Honesty constraint discovered during repair

A "qualified ADV" requires stored per-session **share volume** with clocks.
The admitted Related daily store (`services/related_price_series.py`) validates
volume at ingest but persists **close-only bars** (`{date, close}`), and the
chain payloads carry per-contract option volume only. So no qualifying source
exists today; per the U13-adjacent acceptance wording, the repair returns typed
unavailable/partial status instead of an invented or frozen-scale substitute.
`Frozen model feature scales/locked kernels untouched — compute helpers
unmodified (they are read-path for U12).`

## Repair (trinity.py only)

- `_qualified_adv_shares(ticker, raw)`: returns `(adv, provenance)` only from
  qualified evidence; today nothing qualifies → `(None, {status, reason:
  no_qualified_adv, detail})`. When an admitted volume store exists, qualify
  here with source/session-count/as-of.
- `gamma_imbalance`: emitted with `status: ok` + `adv_shares` + `adv_provenance`
  only when qualified; otherwise typed `unavailable` (nulls, explicit
  interpretation); compute exception → typed `partial` + logged warning
  (silent `pass` removed).
- `cross_asset_spillover`: typed `unavailable` / `no_separate_spx_measurement`
  — the selected ticker's value is never substituted for SPX again.
- `flip_metrics` (no ADV input) preserved with its own typed-partial guard.
- Existing keys/layout otherwise unchanged; `404` behavior, metric emission,
  and `/api/trinity/align` untouched.

## Receipts

- RED: `../evidence/u12-red.log` (exit 1, 4 failed — counterexamples real).
- GREEN: `tests/unified/test_trinity_provenance.py` 4/4 pass
  (`../evidence/u12-green.log`): distinct-ticker constant refusal, typed
  unavailable GI, spillover self-substitution refusal, typed partial on
  injected compute failure (with qualified ADV injected).
- ruff clean on both files.
- Neighbor/final run: `tests/unified` + `test_v3_costsave.py` +
  `test_heatseeker.py` + `test_heatseeker_v2.py` + `tests/server/` — see
  `../evidence/u12-final.log` (result recorded below after completion).
  Note: these legacy suites run under conftest `TESTING=1` (burst limiter
  off); running them with the limiter force-enabled makes `/api/trinity` +
  `/api/movers` 429 — that failure mode is an artifact of overriding TESTING,
  not of this change. (`/api/trinity` GET reads remain burst-limited by design;
  they were not in the admitted dashboard families, and U13's verified scope
  did not extend them.)

## Adjacent observations (recorded, NOT in my write scope — not edited)

Identical unqualified-ADV patterns exist outside U12's selector:
`routes/microstructure.py:176` (constant 75M), `routes/steal_three.py:222`
(constant 75M); `routes/heatseeker.py:192`, `routes/gex_analysis.py:167`,
`services/morning_briefing.py:733` use a fixed 3-ticker lookup table. These
need owner-decided scope before any repair; recorded here as exact pointers.

## Status

Slice complete and pinned in my lane → requesting **OpenCode independent review**
of `routes/trinity.py` + `tests/unified/test_trinity_provenance.py` against
baseline `8194eca4`. Remaining U12 scope (independent cross-asset provenance
wiring when a qualified SPX-imbalance/ADV evidence source exists) noted openly.
