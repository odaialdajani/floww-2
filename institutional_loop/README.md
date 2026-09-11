# Institutional loop — launch pack for 4 parallel agents

Prop-firm-grade rebuild of Tidehunter Pro on paid Public data. Read in this order:

1. `MASTER_PLAN.md` — objective, laws, paper→build map (§3), target architecture, 24h runbook, gates, risks.
2. `CONTRACTS.md` — frozen shapes (v1). Propose changes in LEDGER; unanimous to amend.
3. Your brief: `AGENT_A_SIGNALS.md` (quant) · `AGENT_B_DATA.md` (feeds) · `AGENT_C_MONEY.md` (capital) · `AGENT_D_PROOF.md` (gate).
4. `LEDGER.md` — running record (D owns). Post ready + claims in Hour 0–1.

## Launch (one prompt per agent)

> You are [Agent X] in `/Users/nav/Documents/GitHub/floww`. Read `institutional_loop/MASTER_PLAN.md`, `institutional_loop/CONTRACTS.md`, and `institutional_loop/AGENT_X_*.md`, then post your ready note + first 3 task claims to `institutional_loop/LEDGER.md` and start task 1. Loop discipline: plan → failing test → patch → module suite + ruff → commit (`type(scope): subject`, HEREDOC evidence) → push → ledger line. Pull --rebase often. You may READ any file; you may WRITE only your owned files (§5 of the plan). Invoke superpowers skills (TDD, systematic-debugging, verification-before-completion) as you work. Syncs at hours 6/12/18 run by Agent D — be rebased and green. Escalate secrets/frozen-file needs/vendor outages to Nav via the ledger immediately. Work until the 24h final gate or until D posts HANDOFF.

## Who owns what (firewall)
- A: flow_signing/flow_toxicity/flow_skew (NEW), flow_quality, scanLogic.js
- B: public_*, cache/fetch, kyle/amihud/vpin-bars, flowseeker+public routes, server sweep region, Blademap.jsx
- C: calibration/outcomes/bridge/desk/journal/sizing/hygiene, trade routes, alert levels only
- D: chaos/perf/replay/observability/health/docs/ledger/merges — and nothing else

## Loop discipline (amended: staging hygiene is enforced)
plan → failing test → patch → module suite + ruff → `scripts/loop_guard.sh stage <YOU>` (never `add -A`/`commit -a`) → commit (`type(scope): subject`, HEREDOC evidence) → push → ledger line. Owners: `institutional_loop/OWNERSHIP.md`. SHARED files need `LOOP_SIGNOFF="<date> <owner>: ok"` + a LEDGER line. D runs `check-staged` at every sync.

## Kill switches
`FLOWW_PUBLIC_SWEEP=0` stops the background sweep. Any agent may stop the loop by posting `HALT: <reason>` to LEDGER (all agents check it each task).
