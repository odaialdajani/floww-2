# /prompt2 — Interactive Prompt Formulator & Executor (floww / Confluence Decoder)

## MISSION

Turn a rough idea into a precise, elaborate, high-quality prompt through interactive clarification —
then optionally **execute it via plan mode**, clearing survey noise from context and applying the
prompt as a clean directive.

## ACTIVATION

```
/prompt2 <rough idea or description>
```

**Examples:**
- `/prompt2 add a DTE filter to the Tidehunter Pro flow feed`
- `/prompt2 the ML predict route is slow, cache it`
- `/prompt2 expose the quant signal catalog as an endpoint`

**Key difference from `/prompt`:** after formulation, it offers to execute the prompt immediately
through plan mode — resetting context so implementation starts clean.

---

## ORCHESTRATION MACHINERY (read this before Phase 5)

This project's fan-out machinery is **parallel `Agent` calls in a SINGLE message** for independent
work, and the **`Workflow` tool** for deterministic multi-phase or looping orchestration.

- `TeamCreate` does not exist. There is no "agent teams" mode to restart Claude Code for. Never tell
  the user to restart — never wait for a feature that isn't there.
- **HARD RULE: spawn all independent agents in ONE message.** Sequential spawning of independent
  agents kills the parallel-verification point.
- Use `subagent_type: Explore` for read-only investigation and audits, `general-purpose` for work that
  writes files. Continue a live agent with `SendMessage`. Use `isolation: 'worktree'` only when two
  agents would otherwise edit the same files.
- A slash command that instructs a Workflow counts as the opt-in to run one.

**Lane rule (this repo, non-negotiable):** every generated multi-agent prompt must assign each agent
a **disjoint file lane** and state it explicitly. Commits are **pathspec only** (`git add <exact
files>`) — never `git add -A` / `git add .`, because the working tree routinely holds another lane's
in-flight work. Reference: `.planning/AGENT_CONTRACT.md` §2.

---

## EXECUTION PROTOCOL

### Phase 1: Intent Extraction (ALWAYS DO FIRST)

Read the rough idea carefully. Identify:
- **Domain**: which layer does this touch? (FastAPI route, service, ML pipeline, DuckDB/Mongo
  ingestion, React surface, backtest, deploy/CI, docs)
- **Surface**: which of the six user-facing tabs, if any? Solstice (page id `heatseeker`), Triad
  (`trinity`), Zenith (`skylit`, display-only), Tidehunter Pro (`flowseeker-pro`), Portfolio, Journal.
  Source of truth: `frontend/src/shell/navConfig.js`.
- **Action**: build, fix, refactor, analyze, audit, document
- **Ambiguities**: what is unclear or could go multiple ways
- **Assumptions**: what you'd have to assume without clarification

List your understanding back in 2-3 bullets BEFORE asking questions.

---

### Phase 1.5: Session Rename + Phase Gate (AUTOMATIC)

#### A) Active-Phase Check (MANDATORY)

This repo tracks work through GSD, not a single "priority tab". **Read `.planning/STATE.md` (current
phase) and `.planning/ROADMAP.md` (ticket list) before judging priority.** Do not assume — these files
move.

> **Trust nothing on sight.** `.planning/STATE.md` currently contains two contradictory "Tests:"
> blocks; `ROADMAP.md` §6.4 is headed COMPLETE with all sub-boxes unchecked; Phase 4 is [ACTIVE] in
> ROADMAP but [GATED] in its own `PLAN.md`; `docs/ROUND10_PLAN.md` still says "Draft" though its P0s
> closed in August. Open the phase directory (`.planning/phases/<slug>/PLAN.md`) before quoting status.

Classify the task:
- **IN PHASE** → it advances an open ticket in the current `.planning/ROADMAP.md` phase, or it fixes a
  bug on a shipped surface.
- **OUT OF PHASE** → it belongs to a later phase, a closed phase, or nothing in the roadmap
  (speculative refactors, new panels, cleanup, docs-only, non-blocking security work).

**If OUT OF PHASE, stop and warn:**

```
PHASE GATE WARNING
Current GSD phase (.planning/STATE.md): [phase + status]
This task advances: [what it actually advances, or "nothing in the current phase"]
Reason it's outside: [why]

Do you want to:
1. "Proceed anyway" -> Continue; the session name is tagged [DEFERRED]
2. "Abort"          -> Stop here, log the idea into BACKLOG.md instead
3. "Reframe"        -> Rephrase to target an open ticket in the current phase
```

Do NOT invent a priority surface. The repo does not declare one — if the evidence is ambiguous, say
so and ask.

#### B) Session Rename

Generate a short label (3-8 words) with an area-aware prefix:

| Prefix | Meaning |
|---|---|
| `[SOLSTICE]` | Heatseeker surface — `frontend/src/components/heatseeker/`, `backend/routes/heatseeker*.py` |
| `[TRIAD]` | Trinity confluence view — `backend/routes/trinity.py` |
| `[ZENITH]` | Skylit GEX grid (display-only; data comes from the others) |
| `[TIDEHUNTER]` | Flowseeker Pro — `frontend/src/components/flowseeker/`, `backend/routes/flowseeker.py` |
| `[TRADING]` | Portfolio / Journal surfaces |
| `[BACKEND]` | Routes/services with no single surface owner |
| `[ML]` | `backend/services/ml/`, model training, backtest |
| `[DATA]` | Ingestion, DuckDB, Mongo, the Public API → cvserver → yfinance → Databento chain |
| `[INFRA]` | deploy/, CI, Docker, Caddy, Prometheus/Grafana |
| `[DEFERRED]` | Outside the active phase — user chose to proceed anyway |

**Rules:** strip filler ("I want to", "please", "can you"); lead with the action verb; name the
surface if not obvious.

**How to rename:** output the title so it appears in the conversation —

```
Session: [TIDEHUNTER] Add DTE Filter To Flow Feed
```

— and set the terminal title. On this Windows machine use whichever shell you're in:

```bash
# Bash tool
printf '\033]0;[TIDEHUNTER] Add DTE Filter To Flow Feed\007'
```
```powershell
# PowerShell tool
$Host.UI.RawUI.WindowTitle = "[TIDEHUNTER] Add DTE Filter To Flow Feed"
```

---

### Phase 1.9: "Just Rephrase" Fast Path

If the user says **"just rephrase"** (or "quick rewrite", "tighten it up", "just clean it up"), skip
the survey and:

1. Take the raw idea as written
2. Apply the quality standards below as a filter: remove weasel words ("maybe", "try to", "if
   possible"); make the objective unambiguous; add priority colors to every requirement; add an
   "Out of Scope" section based on what the idea does NOT say; add a verification method using this
   repo's real commands
3. Infer tone from the raw idea (aggressive language → Aggressive, careful → Cautious, default →
   Surgical)
4. Output the tightened prompt in under 60 seconds
5. Skip Phase 2 (Survey), Phase 3 (Generation), Phase 3.5 (Stress Test) — go straight to Phase 4
   (Review). On approval, skip Phase 4.5 (Nuclear Audit) and go straight to Phase 5 (Execution).

This is the escape valve for when the full process is overkill.

---

### Phase 2: Interactive Survey (USE AskUserQuestion)

Ask in **batches of 1-4**. Never more than 4 at once. Multiple rounds if needed.
Keep questions short and in plain trader English — no engineering vocabulary.

#### Round 1: Scope & Output Type (ALWAYS ASK)

**Question 1 — Output Format (MANDATORY FIRST):**
```
"What type of prompt output do you want?"
- "Single Prompt"  -> one refined, standalone prompt for one agent/session
- "Multi-Agent"    -> a fan-out plan: parallel Agent calls in one message, or a Workflow
                      for phased/looping runs
- "Both"           -> generate both for comparison
```

**Question 2 — Scope:**
```
"How broad is this?"
- "Narrow/Focused"      -> one file, one route, one component
- "Medium"              -> several files, one system (e.g. a route + its service + its tests)
- "Broad/Architectural" -> cross-cutting, backend + frontend, or a design decision
```

#### Round 2: Detail & Constraints (BASED ON ANSWERS)

Pick 2-4. **Always include Tone.**

**Tone (ALWAYS ASK):**
```
- "Cautious"    -> ask before every risky change, verify assumptions, safety over speed
- "Aggressive"  -> ship fast, decide autonomously, only ask if truly stuck
- "Exploratory" -> research first, present options before committing
- "Surgical"    -> touch only what's specified, zero side effects, minimal footprint
```

**Specificity:** high-level direction / step-by-step / pseudocode-level.

**Constraints:**
```
- "Yes, I'll specify"        -> user provides constraints
- "Use project rules"        -> Phase 3 auto-reads CLAUDE.md + .planning/AGENT_CONTRACT.md
                                (+ .planning/codebase/CONVENTIONS.md when style matters) and
                                embeds ONLY the applicable rules
- "Minimal constraints"      -> let the agent be creative
```

**Error handling:** defensive / happy path / research first.

**Context window:** self-contained / reference external docs / minimal.

#### Round 2.5: Domain-Adaptive Questions (AUTOMATIC)

Based on the domain detected in Phase 1, ask **1-2** questions a generic survey would miss:

| Domain detected | Extra questions |
|---|---|
| **Options chain / GEX / Greeks** | "Which GEX scale does this touch — the display numbers or the model features?" (they are deliberately different; see the dual-scale note in Phase 3) |
| **ML / model / prediction** | "Does this change the feature vector or the model artifacts? If yes, does it require a retrain?" |
| **FastAPI route** | "On failure, should it return partial data or a real error status the UI can show?" |
| **Data ingestion / DuckDB / Mongo** | "Should the operation be idempotent? What happens if it runs twice on the same day?" |
| **Data source / fallback chain** | "If the Public API is down and it falls through to cvserver/yfinance, should the UI show degraded-source labelling or fail loudly?" |
| **React surface** | "How is visual correctness verified — screenshot, manual check in the running app, or a jest assertion?" |
| **Backtest / signals** | "What's the acceptable tolerance, and which report file should the result land in?" |
| **Deploy / CI** | "Does this need to keep working on the Oracle free-tier ARM target?" |
| **Cross-cutting refactor** | "What's the blast radius — which of the six surfaces and which tests must still pass?" |

Skip this round if nothing matches.

#### Round 3: Multi-Agent Specifics (ONLY IF "Multi-Agent" or "Both")

```
"How should the agents be organised?"
- "Parallel + Merge" -> independent lanes, all spawned in one message, you merge results
- "Pipeline"         -> a Workflow: each item flows through stages (find -> verify -> fix)
- "Find then Verify" -> a Workflow: finders fan out, then adversarial verifiers attack each finding
- "Let me decide"    -> include guidance, pick based on the task
```
```
"How many agents?"
- "Small (2-3)"      -> only split if clearly independent
- "Moderate (4-6)"   -> one specialist per concern
- "Let the lead decide"
```
```
"Should agents plan before implementing?"
- "Yes" / "No" / "Only for risky changes (frozen files, ML, money path)"
```

#### Round 4: Refinement (OPTIONAL)

If the answers reveal more ambiguity, ask 1-2 more targeted questions. Otherwise generate.

---

### Phase 3: Prompt Generation

#### Priority Color System (MANDATORY on ALL generated prompts)

| Tag | Meaning | When |
|---|---|---|
| 🔴 **P0 — CRITICAL** | Must-have. Failure here = task failed. | Core objective, hard constraints, breaking-change risk |
| 🟡 **P1 — IMPORTANT** | Significant impact if skipped. | Supporting requirements, error handling, edge cases |
| 🟢 **P2 — NICE-TO-HAVE** | Could defer without harm. | Cleanup, optimization, style, docs |
| ⚪ **INFO** | Context only. Not actionable. | Background, references |

Every requirement and constraint line gets a tag. Higher priority always wins a tradeoff. If
everything is the same priority, you haven't force-ranked hard enough.

#### Project rules worth embedding (cherry-pick, never dump the whole file)

When "Use project rules" is selected, read `CLAUDE.md`, `.planning/AGENT_CONTRACT.md`, and the
relevant file in `docs/adr/` (6 Accepted ADRs — model promotion, data-source policy, backtest equity,
CORS, test discipline, coupling) and embed only what applies.

**Two clauses of the law files are macOS-era and SUPERSEDED here — never let them into a generated
prompt:** Contract §1's canonical-path rule (`/Users/nav/Documents/GitHub/floww`, "STOP and re-cd")
would halt every agent on this Windows clone; and Contract §7 / CLAUDE.md's
`backend/.venv/bin/python3` does not exist. Use `C:\Users\DARK HERO\Desktop\FLOWW2.0` and
`backend/.venv313/Scripts/python.exe`. Everything else in the contract still binds.

The rules that most often apply:

- 🔴 **Frozen files — STOP and ask Nav first:** `backend/services/ml/inference.py` (surgical bug fixes
  only, justified in the commit body) · `backend/services/dash_ui.py` · `frontend/src/App.js` (1128
  lines, concurrent WIP, surgical only with explicit approval) · `frontend/.env` ·
  `frontend/package.json` · `frontend/craco.config.js` · model artifacts under `backend/models/`.
  (`backend/tests/conftest.py` — freeze **WAIVED**, R10 P0.1.)
- 🔴 **Test discipline:** never add `@pytest.mark.skip` / `xfail` / `it.skip()` to a previously-passing
  test. If your change makes a passing test fail, the change is wrong — revert and find root cause.
  A test you write must fail before the fix and pass after.
- 🔴 **Anti-fabrication:** every claim carries real command output. Round 7's fabricated completion
  log is the negative-example floor.
- 🔴 **Pathspec commits only** (`git add <exact files>`, never `-A`/`.`); anti-skip gate after every
  push: `git fetch origin && git log origin/main --oneline -1 | grep "<subject>"` — empty grep means
  the push silently failed, STOP.
- 🔴 **Forbidden git ops:** `push --force`/`--force-with-lease`, `commit --no-verify`, `commit --amend`
  on someone else's commit, `rebase --abort`, `rebase -i`, `reset --hard`, `checkout .`, `restore .`,
  `clean -fd`.
- 🔴 **MONEY PATH — paper only, with a concrete enforcement point.**
  `backend/services/order_router.py` refuses to submit a real order unless
  `FLOWW_ENABLE_LIVE_SCHWAB == "1"` (`backend/routes/live_trading.py` is the route surface,
  `backend/tests/services/test_order_router_gate.py` pins it). Any prompt that could lead an agent to
  remove, invert, default-on, or bypass that check must say so explicitly in Out of Scope. Never
  describe it as dead Schwab code.
- 🔴 **Real live path only.** No synthetic/demo/fake data. `qc/audit/truth_audit.sh` runs first in CI
  with 12 rules keyed to the **commit message** — its `np.random.` rule greps only `backend/ml*.py`,
  a "refactor" subject fails if `backend/server.py` passes 3532 lines, and rules 9-12 reject model
  meta JSON with empty baselines, Sharpe > 5, < 50 samples, or accuracy > 0.95.
- 🟡 **Silent failure ("GSD #11") is a MANUAL rule, not an enforced gate.**
  `.github/workflows/lint.yml` has a step for it, but its grep is broken and it never fires —
  `backend/server.py` already carries 11 unjustified silent excepts with CI green. Convention:
  `# silent by design: <reason>` on the line after `except Exception:`.
- 🟡 **Dual GEX scale — do NOT "fix".** `services/gex_aggregator.py` is dollar-GEX (`spot²`, display);
  `services/gex_history.py` is feature-GEX (`spot¹`, ML features). Same field name `gex_total`,
  different scale, pinned by `tests/services/test_gex_aggregator_oracle.py`. `_RISK_FREE = 0.045` and
  `_IV_FALLBACK = 0.20` are **model-locked**.
- 🟡 **Schwab as a DATA FEED is out** (mock-only, no live key) — this says nothing about the execution
  gate above, which is live. **Databento `auth_account_locked` is a vendor-side account lock, not a
  code bug** — do not send an agent to chase it.
- 🟡 **ADR-0005** makes the broad `data_source` taxonomy assertion in the heatmap tests deliberate —
  never write a prompt telling an agent to tighten it. **ADR-0001** makes the fail-closed baseline
  gate and Sharpe cap in `backend/services/ml/gate.py` policy, not magic numbers.
- ⚪ **React 19** (19.2.8), **no TypeScript** in `frontend/src`, **no `pages/` directory**; routing is
  a `page` string + `?page=` whitelist inside the frozen `App.js`, not React Router. Frontend linting
  is disabled on purpose (craco strips `ESLintWebpackPlugin`), so never ask for a `lint` script.
- ⚪ **Never quote a stale gate as working.** `qc/verify.sh`, `qc/audit/security_regression.sh`, and
  every path rule in `.claude/settings.json` are macOS-authored and inert or broken here — including
  the deny rules meant to protect the frozen files.

#### For Single Prompt Output

```markdown
## Generated Prompt

### Context
⚪ [Background the agent needs — repo root C:\Users\DARK HERO\Desktop\FLOWW2.0, relevant surface, relevant files]

### Objective
🔴 [Clear, specific statement of what to accomplish]

### Requirements (ranked)
1. 🔴 [non-negotiable core]
2. 🟡 [important but not blocking]
3. 🟢 [nice to have]

### Constraints (ranked)
- 🔴 [hard constraint — violating this = failure]
- 🟡 [soft constraint]

### Tone
[Cautious / Aggressive / Exploratory / Surgical]

### Out of Scope (DO NOT TOUCH)
- [specific files, features, systems — always name the frozen files that are near this work]
- [always: data/github-repos/ (vendored third-party clones), backend/models/ artifacts, .venv*, node_modules]

### Project Rules (auto-injected when "Use project rules" selected)
- 🔴 [applicable rule from CLAUDE.md / .planning/AGENT_CONTRACT.md]
- 🟡 [applicable gotcha]

### Success Example (what GOOD looks like)
[Concrete enough that someone can look at the result and say "yes, that matches"]

### Failure Example (what BAD looks like — DO NOT DO THIS)
[The antipattern. The contrast makes expectations crystal clear.]

### Checkpoints (Medium/Broad scope only)
1. After [step N]: verify [specific thing] before continuing
2. Before the final step: run [test] to validate everything so far

### Thinking Hints
Think about [X] before deciding [Y]. Consider [Z] as a complication.

### Escape Hatches
- If [blocker]: do [action]
- If unsure about [ambiguity]: ASK rather than guess
- If a file isn't where expected: check [alternative] before failing
- If tests fail unexpectedly: report the failure — do NOT silence, skip, or xfail a test

### Expected Output
[What the final deliverable looks like]

### Verification (use this repo's REAL commands)
- Prereq:   MongoDB listening on localhost:27017 — backend/tests/conftest.py builds a Motor
            client per test; without it you get mass DB failures that are not your change
- Backend:  cd backend && ./.venv313/Scripts/python.exe -m pytest tests/<path> -v
- Frontend: cd frontend && CI=true npx craco test --watchAll=false --testPathPattern="<name>"
- Lint:     cd backend && ./.venv313/Scripts/python.exe -m ruff check .
            (ruff is not installed by default — install once with
             ./.venv313/Scripts/python.exe -m pip install "ruff==0.15.22")
- Endpoint: cd backend && ./.venv313/Scripts/python.exe -m uvicorn server:app --port 8000
            (there is NO project uvicorn on PATH — a bare `uvicorn` resolves to an unrelated
             venv without this backend's dependencies and dies on import), then curl the route
- Truth:    bash qc/audit/truth_audit.sh

### CI gates with no local command — state them in the prompt anyway
- 🟡 bandit runs hard and unmasked on backend/ (tests excluded): no new shell=True, eval/exec,
     hardcoded credential, or unverified-TLS call. B608 (SQL injection) is skipped by the config,
     so an f-string query passes CI and is still a bug.
- 🟡 Coverage: CI runs pytest with --cov=. and pyproject sets fail_under = 60 — new untested
     backend code can fail the job with every test passing.
- 🟡 CI's backend job pins Python 3.11 (only lint uses 3.13, and you run 3.13.15 locally) —
     write 3.11-compatible syntax or it passes here and fails CI at import.
- 🔴 Any new third-party backend import must be added to backend/requirements.txt in the same
     change; CI and Dockerfile.backend install only from that file, then run `import server`.
```

> **Interpreter warning to carry into every generated prompt:** the only working backend interpreter
> on this machine is `backend/.venv313/Scripts/python.exe` (Python 3.13.15). `backend/.venv` is a
> bare Python 3.11 with no pytest, and `backend/.venv/bin/python3` — the path CLAUDE.md and
> `.claude/settings.json` still name — **does not exist on Windows**. Any prompt that hands an agent
> the CLAUDE.md command will produce an agent that cannot run a single test.

#### For Multi-Agent Output

```markdown
## Generated Multi-Agent Prompt

[Mission in one sentence.]

### Fan-out shape
[Parallel Agent calls in ONE message  |  Workflow (phases: ...)]

### Agents
- **[Role 1]** (`Explore` | `general-purpose`): [focus]. **Lane:** [exact files/dirs it owns.]
- **[Role 2]**: [focus]. **Lane:** [exact files/dirs it owns.]

Lanes MUST be disjoint. No two agents may write the same file.

### Task Board
1. 🔴 **Task 1** — Owner: [Role] · Blocked by: none · Deliverable: [what it returns]
2. 🟡 **Task 2** — Owner: [Role] · Blocked by: Task 1 · Deliverable: [...]

### Tone
[Cautious / Aggressive / Exploratory / Surgical]

### Out of Scope (DO NOT TOUCH)
- [frozen files near this work]
- data/github-repos/, backend/models/ artifacts, .venv*, node_modules, kanban/, round9*/round11*/

### Coordination Rules
- Every agent runs `git status --short` first and leaves other lanes' modified files alone
- Pathspec commits only: `git add <exact files>`. Never `git add -A` / `git add .`
- Blocked agent: report to the lead, do NOT silently stall
- Self-HALT: 15 min without progress -> write to kanban/cards/agent_<n>_status.md
  as `[timestamp] AgentId :: status :: note :: HEAD=sha`
- Two agents needing the same file: the lead arbitrates ownership

### Success Criteria
- [ ] [Criterion 1 — with the real command that proves it]
- [ ] [Criterion 2]

### Success / Failure Examples
[GOOD outcome] / [BAD outcome — the antipattern]

### Per-Agent Instructions
#### Agent: [Role 1]
[Full prompt: context, objective, owned files, constraints, verification command]
```

---

### Phase 3.5: Self-Adversarial Stress Test (AUTOMATIC — before showing the user)

Try to break your own output:

1. **Ambiguous sentences** — can any requirement be read two ways? Rewrite it.
2. **Missing failure scenarios** — file missing? function renamed? Mongo empty? market closed? API key
   absent? Add escape hatches.
3. **Contradicting requirements** — do any two conflict? Does a constraint make a requirement
   impossible?
4. **Scope creep triggers** — could an eager agent over-deliver? Tighten the wording.
5. **Priority misranks** — any 🟢 that's actually critical, or 🔴 that's actually optional?
6. **Repo-reality check** — does every file path, route, and command in the prompt actually exist?
   Grep/glob to confirm before shipping the prompt. A prompt that names
   `backend/.venv/bin/python3`, a bare `uvicorn`, a `frontend/src/pages/` folder, an `npm run lint`
   script, `project_oracle/*.pt`, or a TypeScript file is wrong — none of those resolve here.
7. **Baseline honesty** — if the prompt tells an agent what "already fails", it must be right.
   Current truth: backend has ~3-6 pre-existing failures; **frontend is 280/280 green across 44
   suites**, so any frontend failure is a real regression (the `continue-on-error` comment in
   `ci.yml` citing 12-18 failures is stale per `BACKLOG.md` K4). Never hand an agent a permission
   slip for a break it caused.

**Devil's Advocate Pass:** challenge the prompt's biggest assumption — "this assumes [X]; is that true
right now?" Output it as a ⚪ INFO note at the end.

**Token Budget Check:** words × 1.3. Over ~2,000 tokens → flag as heavy, suggest trimming INFO.
Over ~4,000 → warn the user. Add the estimate to PROMPT STATS.

Fix what you find, then proceed.

---

### Phase 4: Review & Iterate

```
"How does this prompt look?"
- "Perfect, use it" -> from the fast path, skip to Phase 5; otherwise go to Phase 4.5
- "Needs tweaks"    -> ask what to change, regenerate
- "Too verbose"     -> condense while keeping precision
- "Too vague"       -> add specificity in the identified areas
```

On regeneration, show a side-by-side diff:
```
CHANGES v1 -> v2:
+ Added:   [new requirement or constraint]
~ Changed: "[old wording]" -> "[new wording]"
- Removed: [removed item]
```

Max 3 refinement rounds, then output the best version.

---

### Phase 4.5: Nuclear Audit (Scope-Gated)

| Scope | Audit depth |
|---|---|
| **Narrow/Focused** | **Skip** — Phase 3.5 self-review is enough. Go to Phase 5. |
| **Medium** | **Lightweight (3 auditors)** — Correctness, Project Rules Compliance, Execution Feasibility |
| **Broad/Architectural** | **Full (5 auditors)** — all five below |

Deploy as **parallel `Agent` spawns in a SINGLE message** (`Explore` for read-only auditors), or a
**Workflow** when rounds/loops are needed.

**⚠️ HARD RULE: all audit agents spawn in ONE message.** Never sequential — independent parallel
verification is the whole point.

**Deduplicate with Phase 3.5:** self-review already caught wording, token budget, priority misranks,
and scope-creep phrasing. Auditors focus on what self-review cannot catch — compliance with the
external law files, codebase-level feasibility (grep/glob to verify paths exist), structural blind
spots, and whether the prompt captures the user's actual intent.

**Auditor 1 — Correctness:** does the prompt achieve what the user asked? Anything lost in
translation? Do the success criteria actually prove completion, or could they pass while the task is
unfinished? Any logical contradictions? Does the verification method verify the right thing?

**Auditor 2 — Blindspot & Gap Hunter:** missing edge cases (empty option chain, market closed, null
Greeks, missing API key, Mongo empty, model artifact absent)? Unaddressed failure modes when the
Public API → cvserver → yfinance → Databento fallback chain degrades? Implicit assumptions? Race
conditions or ordering dependencies? What would a devil's advocate say?

**Auditor 3 — Project Rules Compliance:** read `CLAUDE.md` and `.planning/AGENT_CONTRACT.md`. Does the
prompt respect every frozen file? Test discipline? Pathspec-commit and anti-skip rules? Paper-only?
Real-data-only? Does it accidentally invite a "fix" to the dual GEX scale or the model-locked
constants? Does it reference the right files, architecture, and conventions
(`.planning/codebase/CONVENTIONS.md`)?

**Auditor 4 — Scope & Drift:** is the scope razor-sharp? Are "Out of Scope" boundaries explicit enough
to stop an eager agent? Would executing this touch `data/github-repos/`, model artifacts, or another
lane's in-flight files? Is every requirement necessary, or is there gold-plating? Are the priority
colors right?

**Auditor 5 — Execution Feasibility:** can this run in one session? Are the token estimates realistic?
**Do the file paths, routes, function names, and commands actually exist — verified by grep/glob, not
assumed?** Are inter-requirement dependencies acknowledged? For a multi-agent prompt, are the lanes
truly disjoint and right-sized?

#### Audit Output Format

```
==========================================================
  NUCLEAR AUDIT REPORT
==========================================================
Prompt:    [session title]
Auditors:  [3 or 5]
Verdict:   PASS / PASS WITH WARNINGS / FAIL
----------------------------------------------------------

CRITICAL (must fix before execution):
1. [Finding] — [auditor] — [why it matters]

WARNINGS (should fix):
1. [Finding] — [auditor] — [suggested fix]

SUGGESTIONS (optional):
1. [Finding] — [auditor] — [improvement]

NOTES (no action):
1. [Note]

PROJECT RULE COMPLIANCE:
- CLAUDE.md laws:              [clear / violations found]
- AGENT_CONTRACT.md:           [clear / violations found]
- Frozen files respected:      [yes / no — which]
- Active phase (STATE.md):     [in phase / deferred, user approved]
- Test discipline:             [clear / violation]
- Paths verified to exist:     [yes / no — which are wrong]

VERDICT REASONING:
[1-2 sentences]
==========================================================
```

#### After the Audit

- **PASS** → go to Phase 5.
- **PASS WITH WARNINGS** → show them, ask "fix these before executing, or proceed as-is?"
- **FAIL** → show all CRITICAL findings. Fix, re-run Phase 4, re-run Phase 4.5. Maximum 2 audit
  cycles; if it still fails, output as-is with all findings attached and let the user decide.

---

### Phase 5: Execution Decision

**If Single Prompt:**
```
"What do you want to do with this prompt?"
- "Execute via Plan Mode (Recommended)" -> enter plan mode with the refined prompt as the
                                            mission; clears survey noise from context
- "Just give me the text"                -> output the final prompt only
- "Execute directly (no plan)"           -> run it now; narrow scope only
- "Save to file"                         -> write it for later
```

**If Multi-Agent:**
```
"What do you want to do with this prompt?"
- "Run it now (Recommended)" -> spawn all planned agents in ONE message, or launch the Workflow
- "Just give me the text"    -> output the final prompt only
- "Save to file"             -> write it for later
```

#### If "Execute via Plan Mode":

1. **Summarize** the refined prompt compactly (context + objective + requirements + constraints) —
   this is what carries forward
2. **Call `EnterPlanMode`**
3. In plan mode, use the refined prompt as the mission: explore with the objective in mind, build the
   plan against its requirements and constraints. The survey back-and-forth is now out of context.
4. **Call `ExitPlanMode`** when the plan is ready for approval
5. On approval, implement

```
WITHOUT plan mode:  [survey noise] + [prompt] + [implementation] = bloated context
WITH plan mode:     [survey noise] -> CLEARED
                    [prompt] -> APPLIED as clean mission
                    [fresh exploration] + [implementation] = focused context
```

#### If "Save to file":

Use this repo's real conventions — do not invent a folder:

| Kind | Path |
|---|---|
| Implementation plan | `docs/superpowers/plans/YYYY-MM-DD-<slug>.md` |
| Research / audit write-up | `docs/superpowers/research/YYYY-MM-DD-<slug>.md` |
| Design spec | `docs/superpowers/specs/YYYY-MM-DD-<slug>.md` |
| Per-phase GSD plan | `.planning/phases/<phase-slug>/PLAN.md` |

There is no `.claude/prompts/` directory in this repo. Ask for the slug, then write.

---

## QUALITY STANDARDS FOR GENERATED PROMPTS

**A good prompt MUST have:**
1. Unambiguous objective — one interpretation of success
2. Measurable deliverables — concrete outputs, not vague goals
3. Explicit constraints — what NOT to do matters as much as what to do
4. Context sufficiency — the agent can start without asking
5. A verification method built from **this repo's real commands**
6. Priority colors on every requirement and constraint

**A good prompt MUST NOT have:**
1. Weasel words — "maybe", "try to", "if possible", "consider"
2. Ambiguous scope — "improve the system", "make it better"
3. Missing edge cases
4. Assumed project knowledge that isn't stated or referenced
5. Contradictions
6. **Any path or command that doesn't exist here** — `backend/.venv/bin/python3`,
   `frontend/src/pages/`, `npm run lint`, a `.ts`/`.tsx` file, `open -a`, `lsof`

**Multi-agent quality:**
1. Clear ownership — every task has exactly one owner and a disjoint file lane
2. No circular dependencies — the task graph is a DAG
3. Right-sized agents — not 3 agents for a 20-line change, not 1 agent for 500 lines across 8 files
4. Stated coordination protocol and a self-HALT rule
5. Failure handling — what happens if one agent gets stuck

---

## OUTPUT FORMAT

```
======================================================
  PROMPT FORMULATOR v2 — RESULTS
======================================================

Session: [PREFIX] <short title>

INPUT (your rough idea):
> [original user input]

PHASE CHECK: In current GSD phase  OR  Outside phase (user approved)
Current phase per .planning/STATE.md: [phase + status]

CLARIFICATION SUMMARY:
- Output type:  [Single / Multi-Agent / Both]
- Scope:        [Narrow / Medium / Broad]
- Specificity:  [High-level / Step-by-step / Pseudocode]
- Constraints:  [Specified / Project rules / Minimal]
- Context:      [Self-contained / Referenced / Minimal]
[If multi-agent] Shape: [Parallel / Workflow-pipeline / Find-then-verify]
[If multi-agent] Agents: [N]

PRIORITY LEGEND: (🔴 P0 | 🟡 P1 | 🟢 P2 | ⚪ Info)

------------------------------------------------------
GENERATED PROMPT
------------------------------------------------------
[The actual prompt — every requirement and constraint
 line prefixed with its priority color]

------------------------------------------------------
PROMPT STATS
------------------------------------------------------
- Word count:          [N]
- Estimated tokens:    [~N]   (HEAVY if >2K, WARNING if >4K)
- Ambiguity score:     [Low / Medium / High]
- Self-containedness:  [Full / Partial / Minimal]
- Priority breakdown:  [N] 🔴  [N] 🟡  [N] 🟢  [N] ⚪
- Stress test:         [N issues found and fixed in Phase 3.5]
- Paths verified:      [N checked, N wrong]
- Tone:                [Cautious / Aggressive / Exploratory / Surgical]

------------------------------------------------------
EXECUTION
------------------------------------------------------
- Mode:   [Plan Mode / Direct / Text Only / Saved]
- Status: [Awaiting decision / Entering plan mode / Complete]
======================================================
```

---

## TIPS FOR USERS

- **Be as rough as you want** — refinement is the whole point
- **Say "skip"** to any question — defaults get used
- **Say "more questions"** for deeper clarification
- **Say "just rephrase"** to skip the survey
- **Use "Execute via Plan Mode"** for anything non-trivial — cleanest implementation context
- **Use "Execute directly"** only for narrow, well-defined tasks
- **Multi-agent is best for:** multi-file changes with clean lane separation, parallel investigation
  across `backend/routes/` + `backend/services/` + `frontend/src/`, and find-then-adversarially-verify
  audits. It is worst for anything that would have two agents editing the same file.

---

## ANTI-PATTERNS TO AVOID

- Do NOT generate a prompt without asking at least the output-format question
- Do NOT ask more than 4 questions in a round
- Do NOT generate vague prompts ("implement the feature properly")
- Do NOT plan more than 6 agents (diminishing returns, linear token cost)
- Do NOT spawn independent agents one at a time — always one message
- Do NOT tell the user to restart Claude Code for "agent teams" — that mode does not exist here
- Do NOT invent a priority surface; read `.planning/STATE.md` and say "ambiguous" when it is
- Do NOT quote a test count from `CLAUDE.md`, `BACKLOG.md`, or `.planning/STATE.md` as fact — they
  disagree with each other. Run the suite or say "unverified"
- Do NOT skip the Nuclear Audit for Medium or Broad scope (Narrow and the fast path skip it by design)
- Do NOT proceed to execution on a FAIL verdict — fix first, then re-audit
- Do NOT enter plan mode without first summarizing the refined prompt compactly
- Do NOT carry raw survey Q&A into plan mode — only the refined prompt carries forward
- Do NOT default to "Execute directly" for broad-scope tasks — recommend plan mode
