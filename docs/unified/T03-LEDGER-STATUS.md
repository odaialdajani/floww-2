# Ledger status at merged head `f1e76e82` (updated 2026-10-08)

Machine re-check (`check-closure.py --check-engineering`): pending is now
exactly **C17** — CLOSED 2026-10-08: admitted per-strike exposure series
shipped (projection counts + read-only endpoint + 6/6 tests + freshness
gate). See `C17/DEFERRAL.md`. The 18 "belongs to another SHA" notes are
the known SHA-strictness on I-tasks accepted at older heads — unchanged.
**T03 → ACCEPTED_AT_SHA** with Cline adversarial review + three hashed
packet-relative receipts (`references/t03-*`). 54 engineering accepted;
7 Nav holds intact. Prior notes below (pending T03; pending T03+C17) are
superseded.


Tool: old-packet `tools/check-closure.py --check-engineering
--candidate-sha f1e76e82...` (read-only structural check, not production
proof). Result: engineering HOLD, commissioning SEPARATE_NAV_HOLDS.

- Structurally accepted: S01–S15, C01–C16 (all).
- Pending engineering: exactly **T03** (needs Cline post-merge adversarial
  review — merged with zero recorded reviews) and **C17** (admitted
  exposure metric, Cline-owned, optional P2).
- I01–I18 accepted at older SHAs; the checker is SHA-strict so they "belong
  to another SHA" at the merge commit. The merge delta vs `8194eca4` is
  5 frontend files only (App mount + Triad desk); no backend/contract/store
  behavior changed, and the new code paths are covered by the 11/11 +
  full-gate runs recorded in U03/MERGED-HEAD-GATE. Formal re-acceptance at
  the merged head belongs to a future frozen-candidate pass, not a silent
  transfer — same rule as the unified harness (no old ACCEPTED_SHA moves
  to new source).
- External holds: NAV-ACCOUNT, NAV-CAPTURE, NAV-MODEL, NAV-NATIVE,
  NAV-VISUAL, NAV-RELEASE, NAV-PAPER-EXEMPT (all Nav).

No OpenCode-executable item remains: every owned task is sealed and every
open item names Cline (T03 review, C17, U06–U08/U10–U12/U15/U16) or Nav
(commissioning) as the actor.
