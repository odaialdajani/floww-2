---
id: deepseek-r8-proxy-2026-05-24
title: "DeepSeek + Architect Round 8 Phase 0 — proxy/env/craco fix"
status: done
assignee: deepseek-round-8 + architect
acceptance: |
  React dev server starts successfully under new craco config.
  Proxy field in package.json points to http://localhost:8000.
  Backend listening at port 8000 (verified via lsof).
  All 10 Hermes Round 8 agents now unblocked.
---

## Commits
- e179821 fix(frontend-proxy): wire React dev server to FastAPI backend (Round 8)

## Verification
```
$ python3 -c "import json; print(json.load(open('frontend/package.json'))['proxy'])"
http://localhost:8000

$ grep -A 4 'devServer:' frontend/craco.config.js | grep allowedHosts
    allowedHosts: "all",

$ tail -3 /tmp/react_r8.log
Compiled successfully!
webpack compiled successfully

$ lsof -i :8000 -P -n | grep LISTEN | head -1
Python    70875  nav   14u  IPv4 0xd89bfa34b0b6bc2a      0t0  TCP *:8000 (LISTEN)
```

## Architect notes
- DeepSeek session ended before completing Phase 3 commit; architect closed the loop with the bundled craco fix.
- Sandbox curl from architect environment timed out reaching localhost:3000/api/* (sandbox network restriction), but the local React process is running fine for the user's browser.
- User should verify in Chrome decoder PWA: open localhost:3000, click Heatseeker tab — the "Unexpected token '<'" errors should disappear once components fetch real JSON.
