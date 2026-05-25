# DeepSeek Round 8 — Proxy/Env Fix (RUN FIRST)

> **HOW TO USE:** Copy everything below the first `═══` line. Paste into DeepSeek.
> This is a SHORT, SURGICAL prompt. Should finish in 5-10 minutes.
> **All 10 Hermes agents BLOCK until this completes.**

═══════════════════════════════════════════════════════════════════════════════

You are a senior frontend infrastructure engineer. ONE mission: make the React
app at `frontend/src/` actually reach the FastAPI backend instead of returning
its own `index.html` for every `/api/*` call.

═══════════════════════════════════════════════════════════════════════════════
DIAGNOSIS (verified by the architect — do not re-diagnose)
═══════════════════════════════════════════════════════════════════════════════

- React dev server runs at `http://localhost:3000`
- FastAPI backend runs at `http://localhost:8000`
- `frontend/src/App.js:56-57`:
    const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
    const API = `${BACKEND_URL}/api`;
- `frontend/.env` does NOT exist; `frontend/package.json` has no `proxy` field
- Result: `BACKEND_URL === undefined` → `API === "undefined/api"` → browser
  treats requests as relative to `localhost:3000` → CRA returns `index.html`
- Every panel that calls an API parses HTML as JSON and crashes with
  "Unexpected token '<', \"<!doctype \"..."

Backend IS healthy:
    $ curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/chain/SPY
    200
    $ curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/heatseeker/flip-zones?ticker=SPY"
    200

═══════════════════════════════════════════════════════════════════════════════
OPERATING RULES (violating = P0)
═══════════════════════════════════════════════════════════════════════════════

  R1. pwd MUST equal /Users/nav/Documents/GitHub/floww. Else HALT WRONG_CLONE.
  R2. NEVER --abort | --reset --hard | --force | --no-verify | rm -rf .
  R3. You touch ONLY these files:
        frontend/.env                  (create, do not modify if exists)
        frontend/package.json          (add proxy field; do not change anything else)
        kanban/cards/deepseek_r8_proxy_$(date +%Y-%m-%d).md  (closure card)
        docs/ROUND8_COMPLETION_LOG.md  (create; one entry)
      Touching ANY other file = HALT.
  R4. Every commit message claim must be backed by a grep/curl output in the
      message body. No fabricated "fix complete" claims.
  R5. NEVER mark a test xfail/skip. If something is broken, HALT.
  R6. Halt format:
        ──── HALT REPORT ────
        Phase: <n> Step: <n.n>
        Reason: <one sentence>
        Output: <verbatim>
        Question: <one specific question>
        ─────────────────────

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY
═══════════════════════════════════════════════════════════════════════════════

  S0.1  cd /Users/nav/Documents/GitHub/floww
        pwd && git remote -v
        EXPECT canonical path + remote.

  S0.2  ls .git/rebase-merge/ 2>&1
        EXPECT "No such file or directory". Else HALT REBASE_IN_PROGRESS.

  S0.3  git pull --rebase origin main
        On conflict: HALT.

  S0.4  git branch backup/deepseek-r8-$(date +%Y%m%d-%H%M%S)

  S0.5  Verify the diagnosis is still accurate (state may have changed):
          ls frontend/.env 2>&1
          grep -c "proxy" frontend/package.json
          grep -n "REACT_APP_BACKEND_URL\|BACKEND_URL = process" frontend/src/App.js | head -3
        EXPECT:
          - ls: "No such file or directory" for .env
          - grep count for "proxy" in package.json: 0
          - App.js references process.env.REACT_APP_BACKEND_URL
        Else: HALT — diagnosis is stale.

  PRINT "PHASE 0 COMPLETE — diagnosis confirmed — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — ADD PROXY (TWO COMPLEMENTARY MECHANISMS, BELT + SUSPENDERS)
═══════════════════════════════════════════════════════════════════════════════

We add BOTH a `.env` (for explicit URL) AND a `proxy` field (for dev-server
convenience). Belt and suspenders so it works in dev, prod, and Docker.

  S1.1  Create frontend/.env:
          cat > frontend/.env <<'EOF'
          # React app -> FastAPI backend wiring (added Round 8)
          # If you run backend on a different port, change this here, NOT in App.js
          REACT_APP_BACKEND_URL=http://localhost:8000
          EOF

  S1.2  Verify:
          cat frontend/.env
        EXPECT exactly the two lines above (plus the comment line).

  S1.3  Read frontend/package.json:
          cat frontend/package.json | head -50

  S1.4  Add the `proxy` field after the `"private": true,` line OR after the
        last top-level scalar field (NOT inside `scripts` or `dependencies`).
        Use a tiny Python script to keep JSON valid:

          python3 -c "
          import json, pathlib
          p = pathlib.Path('frontend/package.json')
          j = json.loads(p.read_text())
          j['proxy'] = 'http://localhost:8000'
          p.write_text(json.dumps(j, indent=2) + '\n')
          print('proxy field added:', j.get('proxy'))
          "

  S1.5  Verify package.json is still valid JSON and has the field:
          python3 -c "import json; print(json.load(open('frontend/package.json'))['proxy'])"
        EXPECT: "http://localhost:8000"

  S1.6  Confirm no other field was harmed:
          python3 -c "
          import json
          j = json.load(open('frontend/package.json'))
          required = ['name', 'version', 'dependencies', 'scripts']
          missing = [k for k in required if k not in j]
          print('missing:', missing or 'none')
          "
        EXPECT: "missing: none"

  PRINT "PHASE 1 COMPLETE — proxy + env added — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — RESTART REACT, VERIFY PROXY ACTUALLY WORKS
═══════════════════════════════════════════════════════════════════════════════

CRA reads the `proxy` field at startup ONLY. Need to restart the dev server.

  S2.1  Check if React dev server is currently running:
          lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | head -3

  S2.2  If running, kill it gracefully:
          # find the PID of `node` listening on 3000
          PID=$(lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | awk '{print $2}' | head -1)
          if [ -n "$PID" ]; then kill "$PID"; sleep 2; fi
          lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | wc -l
        EXPECT: 0 lines remaining.

  S2.3  Start it again in background:
          cd frontend
          nohup npm start > /tmp/react_r8.log 2>&1 &
          cd ..
          sleep 30   # CRA takes ~25s to compile and serve

  S2.4  Verify React is up:
          lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | head -1
        EXPECT: a `node` LISTEN line.

  S2.5  THE CRITICAL TEST — fetch an API endpoint through the proxy:
          curl -s -o /tmp/proxy_test.json -w "STATUS: %{http_code}\nCONTENT-TYPE: %{content_type}\nSIZE: %{size_download}\n" \
            http://localhost:3000/api/chain/SPY
          echo "FIRST 100 BYTES OF BODY:"
          head -c 100 /tmp/proxy_test.json
          echo ""

        EXPECT:
          STATUS: 200
          CONTENT-TYPE: application/json (NOT text/html)
          SIZE: > 1000
          FIRST 100 BYTES: starts with `{` and contains `"contracts"` or `"spot"`

        If CONTENT-TYPE says `text/html` or body starts with `<!doctype`:
        the proxy is NOT working. HALT — DO NOT COMMIT.

  S2.6  Test a second endpoint to be sure:
          curl -s -o /tmp/proxy_test2.json -w "STATUS: %{http_code}\nCONTENT-TYPE: %{content_type}\n" \
            "http://localhost:3000/api/heatseeker/flip-zones?ticker=SPY"
          head -c 100 /tmp/proxy_test2.json
          echo ""
        EXPECT same as S2.5 (JSON body).

  PRINT "PHASE 2 COMPLETE — proxy verified, JSON returned — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — COMMIT + CLOSURE
═══════════════════════════════════════════════════════════════════════════════

  S3.1  Commit:
          git add frontend/.env frontend/package.json
          git commit -m "fix(frontend-proxy): wire React dev server to FastAPI backend (Round 8)

          Before: GET /api/chain/SPY (from port 3000) returned index.html → JSON.parse failed everywhere
          After:  GET /api/chain/SPY (from port 3000) returns JSON via CRA proxy → port 8000

          Verification:
            \$ curl -s -o /dev/null -w '%{http_code} %{content_type}\\n' http://localhost:3000/api/chain/SPY
            200 application/json
            \$ python3 -c \"import json; print(json.load(open('frontend/package.json'))['proxy'])\"
            http://localhost:8000

          This unblocks all 10 Round 8 Hermes agents who were waiting for /api/* JSON to work.

          Co-Authored-By: DeepSeek <deepseek@floww.dev>"

  S3.2  Push:
          git pull --rebase origin main
          git push origin main

  S3.3  Create Round 8 completion log:
          cat > docs/ROUND8_COMPLETION_LOG.md <<'EOF'
          # Round 8 Completion Log

          Generated $(date -u +%Y-%m-%dT%H:%M:%SZ).

          ## Phase 0 (DeepSeek — proxy fix)

          | Acceptance | Commit |
          |------------|--------|
          | React /api/* calls hit port 8000, return JSON | $(git log -1 --pretty=%h --grep="frontend-proxy") |

          ## Hermes phases (will be filled by Hermes J at close)

          EOF

  S3.4  Closure kanban card:
          cat > kanban/cards/deepseek_r8_proxy_$(date +%Y-%m-%d).md <<EOF
          ---
          id: deepseek-r8-proxy-$(date +%Y-%m-%d)
          title: "DeepSeek Round 8 Phase 0 — proxy/env fix"
          status: done
          assignee: deepseek-round-8
          acceptance: |
            curl http://localhost:3000/api/chain/SPY returns JSON (not HTML).
            All 10 Hermes agents now unblocked.
          ---

          Verified end-to-end via Phase 2 S2.5. Round 8 Hermes fleet may now launch.
          EOF

          git add docs/ROUND8_COMPLETION_LOG.md kanban/cards/deepseek_r8_proxy_*.md
          git commit -m "docs(round-8): DeepSeek proxy-fix closure card + completion log

          Co-Authored-By: DeepSeek <deepseek@floww.dev>"
          git push origin main

  PRINT FINAL REPORT:

        ──── DEEPSEEK ROUND 8 PHASE 0 COMPLETE ────
        proxy field:       http://localhost:8000
        env file:          frontend/.env created
        curl test (3000):  200 application/json (JSON body confirmed)
        commits added:     2
        unblocks:          10 Hermes agents
        ─────────────────────────────────────────

  Final line: "DONE — HERMES FLEET MAY LAUNCH"

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS
═══════════════════════════════════════════════════════════════════════════════

  - You touch FOUR files only (.env, package.json, log, kanban card).
  - You do NOT modify App.js, components, hooks, routes, or anything else.
  - If the proxy doesn't work (S2.5/S2.6 returns HTML), HALT — do not try to "fix
    React" or "fix the backend." The fix is purely config; if it doesn't work,
    the diagnosis is wrong and the architect needs to be re-engaged.
  - You do NOT touch the Dash app at backend/services/dash_ui.py — that is
    Round 7 work, already complete.

END OF PROMPT. BEGIN AT PHASE 0 STEP S0.1.
═══════════════════════════════════════════════════════════════════════════════
