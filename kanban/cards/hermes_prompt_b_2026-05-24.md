---
id: hermes-prompt-b-2026-05-24
title: "Hermes Prompt B — Heatseeker UI completion"
status: done
assignee: hermes-prompt-b
acceptance: |
  8 TDD tests RED → GREEN; 3-column layout assembled; structural verification passed.
---
## Commits
- 7fa9f64 test(heatseeker-ui): failing TDD tests for 8 compute helpers (RED)
- 4a3ad74 feat(heatseeker-ui): implement 8 NaN-safe right-sidebar compute helpers (GREEN)
- 3ebe310 feat(heatseeker-ui): assemble 3-column layout (header + L sidebar + graph + R sidebar)
## Verification
```
$ python -m pytest tests/services/test_dash_ui_three_column.py 2>&1 | tail -1
=== 8 passed in 0.16s ===
$ grep -c '_build_heatseeker_right_sidebar\|_build_heatseeker_header\|_compute_gamma_regime' backend/services/dash_ui.py
9
$ python -m pytest tests/services/ -q --tb=no --ignore=tests/services/ml 2>&1 | tail -1
1940 passed, 50 skipped in 50.88s
$ python -c "from services.dash_ui import _build_heatseeker_right_sidebar, _build_heatseeker_header; s=_build_heatseeker_right_sidebar(748.0, [{'strike':740,'gex':3e8,'oi':5000,'type':'call'},{'strike':755,'gex':-2e8,'oi':4000,'type':'put'}]); print('Panels:', len(s.children))"
Panels: 9
```
## Notes
- All 8 compute helpers NaN-safe (math.isfinite guards)
- Fix: restored @functools.lru_cache decorator on _cached_build_heatmap (was accidentally removed during patch)
- 0 regressions (1940 passed vs baseline ~1940)
- 3-column layout: header strip + left sidebar + center heatmap + right sidebar
- 9 right-sidebar panels: MORNING BRIEFING, KEY LEVELS, STRATEGY, POSITION SIZING, RISK LEVELS, PRE-MARKET CHECKLIST, FLIP ZONES, STACKED NODES, TUG-OF-WAR
- Visual gate: structural verification passed (server-side rendering confirmed); browser JS SPA rendering deferred to human check
