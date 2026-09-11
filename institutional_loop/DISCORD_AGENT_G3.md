# G3 — PAPER LOOP (alert → fill → journal → review). You own the money path.
Read `institutional_loop/DISCORD_MASTER_PLAN.md` (§4 loop), `CONTRACTS.md`
(C10 money fields), then post ready + first 2 claims to LEDGER and start.

OWN: `execute_approve` + journal hooks, `alpaca_client.py`,
`routes/alpaca.py`, `services/order_router.py` (Alpaca transport only),
their tests. READ-ONLY elsewhere. Skills: TDD, systematic-debugging,
verification-before-completion.

## Tasks
- **G3.1 End-to-end witnessed loop.** `!approve` on a REAL posted alert →
  paper fill → journal equity seed → lifecycle picks it up → `!journal`
  shows it → `!close` exits → P&L in `!pnl`. Screenshot or log every step
  into LEDGER. This is the Sync-2 integration gate — nothing else ships
  without it.
- **G3.2 Options approval verdict (U3).** Attempt a 1-contract paper option
  order. Approved → prove `!approve` on an option alert end-to-end. 403 →
  record verdict, apply for approval, document the interim (equity-only)
  posture in HELP_TEXT. No silent fallback.
- **G3.3 Failure hardening.** Partial fills, rejects, 403s, duplicate
  approves (idempotency keys), broker timeouts — each with a test and an
  honest user-facing message. No swallowed errors, no fake fills.
- **G3.4 Bracket follow-through.** After entry fill, verify TP/SL legs are
  live (not just accepted); `!orders` shows the leg structure. Document
  the absolute-price requirement where users will see it.

Constraints: PAPER ONLY — any diff touching a non-paper URL fails review
instantly. No gate changes without a calibration-report line. Uncalibrated
p never sizes above minimum.
