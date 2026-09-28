# Command Code C0–C6 recovery ledger

Session label: Command Code session pasted 2026-09-28.
Runtime: this response was produced by the tool runtime backing this session. I do not have a separate authenticated model/version string in local context, so I record session/branch/SHA evidence rather than asserting Muse Spark 1.3 from the requested name.

## C0 source preservation

- Private original branch intact: `fix/audit-2026-09`
  - HEAD: `bacc9fabb68c464ab1b7a037af5f6d3945b82ec9`
  - Dirty path preserved: `M kanban/BOTTLENECK_ALERTS.md`
  - Dirty blob: `a01f44629be3aefae22e18df8ed98ee7c15be228`
  - Diff is timestamp-only bottleneck metadata.
  - Rollback refs preserved:
    - `pre-rebase-2026-09 = 2750548046c53075b9f31c787062aaeb9623d452`
    - `backup/audit-2026-09-pre-rebase = 2750548046c53075b9f31c787062aaeb9623d452`
- Current origin/main verified without switching another checkout:
  - `origin/main = d905c9d238cc958eefdbb495c0831f723ca29de4`
  - Message: `docs(solstice): stop pinning a SHA the documents own merge invalidates (#72)`
- Observed but not switched/reset:
  - `/Users/nav/Documents/GitHub/floww-2`: `feat/h3-missing-input-neutrality`, `d905c9d2`, dirty bottleneck file
  - `/Users/nav/.opencode/floww2-solstice-ui`: `feat/solstice-ui-cleanup`, `d905c9d2`
- Recovery worktree only:
  - `/Users/nav/.worktrees/cmd-c0-20260928070352`
  - Branch: `cmd/recovery-c0-20260928070352`
  - HEAD: `d905c9d238cc958eefdbb495c0831f723ca29de4`
  - Clean at creation.

## Recomputed relationships

- Prompt SHAs `f77b87dd97cf3a87c3e7c12ed16087ebd079b3ed` and `69d73c958d40a245a9fe89ca816b9ee9e5500bd2` are both ancestors of current `origin/main`.
- Current main is newer: `d905c9d238cc958eefdbb495c0831f723ca29de4`, including #68-#72 lineage.
- `origin/main...fix/audit-2026-09`: `878 43`.
- Merge base: `89fb61b0d8aed1eda879870bcc8c7d8e180604b1`.
- Ancestry/counts are not feature equivalence; main has selective recovery/history-only merges.

## 43-commit classification

Method: `git cherry origin/main fix/audit-2026-09 -v`, commit bodies, patch file lists, production-caller/main-equivalent checks. Classifications only; no ports completed here.

- `c8287907` CI lint/API docs: needs port after current-main gate diff; do not cherry-pick generated docs blindly.
- `ba5be87b` deterministic API-docs gate: needs port after current-main gate diff.
- `9e65b053` OI parser/Net Gamma/signal channel: likely partly already present; minimal behavior diff only.
- `ccb862c2` venv/doc correction: likely obsolete/superseded.
- `0acb3799` delete 13 dead frontend modules: incompatible as whole-commit port; OpenCode/UI-owned.
- `ec1c2aaa` audit claims record: port only missing rows.
- `92b9e4ec` ML schema guard: Hermes/ML lease required.
- `c7d696fb` observability compose fix: check current compose diff.
- `bd5326c7` unwatched alert: check current alert diff.
- `5d9663d2` stop Schwab-as-source docs: doc-only minimal patch possible.
- `2a869af0` Schwab retirement map: port only missing rows.
- `ef1ee1f5` remove Schwab tree-wide: incompatible as whole commit; Hermes owns routes/integration.
- `7ea33753` Schwab tail: incompatible as whole commit.
- `eaf6e2ef` Schwab fixtures: check current fixtures.
- `6c97bb17` sidebar/App contract: OpenCode/UI-owned.
- `3dd5e187` all-Public data contract: Hermes/data lease required.
- `f6f9fec0` blank Triad columns/stale dep: canonical-projection behavior only; no old UI rewrite.
- `ea8f44a4` doc defects: likely obsolete.
- `09963ac6` memory durability pin: Hermes persistence lease required.
- `f39f839a` Charm/WallInspector VEX: trace current wiring; Hermes owns server/routes.
- `8eac5381` fan-out audit docs: likely obsolete.
- `a618813b` warn off metrics.grids.raw fix: port only if guard missing.
- `5156da67` source-inspection flake: likely obsolete.
- `29a53e0a` OI/DUO/DVO surfaces: current main has no DUO/DVO/OI-grid math; minimal canonical port required; C1/C2 gate.
- `de3a3208` eight-surface Triad tabs: old UI absent from main; joint packet only.
- `88b98fc7` import sort: obsolete standalone.
- `3ed61b5d` round-2 Triad docs: likely obsolete.
- `5e042019` Solstice OI/DUO/DVO grid: Hermes/OpenCode coordination required.
- `d70a7ee5` signal-channel fix: check current alerts diff.
- `9c5734c0` #57 docs: obsolete/superseded.
- `c33e635f` where/how wall read: current main has no wall_response module; minimal conditional behavior only; C1.4 gate.
- `f5316174` Play Walls panel: incompatible as UI port; OpenCode owns visuals.
- `b0de55c6` GEX series: current main lacks gex_series; Hermes schema lease required; C1.5/C5 gate.
- `161384cc` ladder/VWAP/chart/camera/mobile: current main lacks session_vwap; UI belongs to OpenCode; C1.2/C1.3 gate.
- `50119c10` VWAP rename: obsolete standalone.
- `85c32d71` DUO/VWAP/chart correctness: DUO math required; VWAP/chart need current-contract adaptation.
- `958bfc68` DUO vs VEX convention: versioned registry only; C2 gate.
- `4f5fd422` one strong wall + rank: deterministic tie policy only; C1.4 gate.
- `3b2f3d42` ladder magnitude: geometry expectations to OpenCode.
- `a40b2958` ADJ/VOL history: Hermes lease required; C1.5/C5 gate.
- `c3bdf4c1` plain-float Greeks: boundary policy; preserve frozen ML; C1.6 gate.
- `155edeac` ADJ = RAW x |delta| pin: canonical registry already has it; port only missing oracle coverage.
- `bacc9fab` mobile tab CSS: OpenCode visual cleanup.

## C1 status

All six remain claims until current code and independent tests establish them. Old frontend/backend counts are stale without collected node IDs, markers, environment accounting, and same-ignore reconciliation.

## C2 VEX distinction

Current main already distinguishes canonical `VEX_1VOLPT`, display/UI dual scale, and frozen ML single-spot scale. Old factor-15 language is separate history and must not silently rescale current data. Use versioned registry IDs/units and schema migration.

## C3 Triad projection

Current TrinityView has GEX/VEX modes, not old private SurfaceTabs/PlayWalls/PriceLadder/GexChart/heatmapSurfaces files. Define WallDeskSnapshot.v1 jointly. Backend owns aggregation/computation; OpenCode owns rendering/selection. No polarity-by-spot-division, inferred zero-gamma root, fake expiry/zero/stale/ticker defaults, or incompatible-population comparisons.

## C4 metric family

Canonical registry already has raw, delta-weighted, session-volume, and window delta-volume metrics with missing-as-unavailable semantics. Do not relabel session volume gamma as volume-delta-adjusted. Window activity needs comparable cumulative observations, reset/retraction exclusion, and visible interval.

## C5/C6 handoff

Fixture and WallDeskSnapshot.v1 packet are not yet published from this slice. Needed: oracle/serialization/route-projection/history tests that fail on old behavior, fixture hashes, exact commands/results, compatibility effects, source-linked limits. Shared route/server mutations remain under Hermes lease. No merge/deploy/trade, broad rebase, force-push, reset, branch deletion authorized or performed.

## Next command

```sh
git -C /Users/nav/.worktrees/cmd-c0-20260928070352 status --porcelain=v1
git -C /Users/nav/.cline/audit-fixes rev-parse fix/audit-2026-09 origin/main
git -C /Users/nav/.cline/audit-fixes rev-list --left-right --count origin/main...fix/audit-2026-09
```

## 43-commit classification

Method: `git cherry origin/main fix/audit-2026-09 -v`, commit bodies, patch file lists, production-caller/main-equivalent checks. Classifications only; no ports completed here.

- `c8287907` CI lint/API docs: needs port after current-main gate diff; do not cherry-pick generated docs blindly.
- `ba5be87b` deterministic API-docs gate: needs port after current-main gate diff.
- `9e65b053` OI parser/Net Gamma/signal channel: likely partly already present; minimal behavior diff only.
- `ccb862c2` venv/doc correction: likely obsolete/superseded.
- `0acb3799` delete 13 dead frontend modules: incompatible as whole-commit port; OpenCode/UI-owned.
- `ec1c2aaa` audit claims record: port only missing rows.
- `92b9e4ec` ML schema guard: Hermes/ML lease required.
- `c7d696fb` observability compose fix: check current compose diff.
- `bd5326c7` unwatched alert: check current alert diff.
- `5d9663d2` stop Schwab-as-source docs: doc-only minimal patch possible.
- `2a869af0` Schwab retirement map: port only missing rows.
- `ef1ee1f5` remove Schwab tree-wide: incompatible as whole commit; Hermes owns routes/integration.
- `7ea33753` Schwab tail: incompatible as whole commit.
- `eaf6e2ef` Schwab fixtures: check current fixtures.
- `6c97bb17` sidebar/App contract: OpenCode/UI-owned.
- `3dd5e187` all-Public data contract: Hermes/data lease required.
- `f6f9fec0` blank Triad columns/stale dep: canonical-projection behavior only; no old UI rewrite.
- `ea8f44a4` doc defects: likely obsolete.
- `09963ac6` memory durability pin: Hermes persistence lease required.
- `f39f839a` Charm/WallInspector VEX: trace current wiring; Hermes owns server/routes.
- `8eac5381` fan-out audit docs: likely obsolete.
- `a618813b` warn off metrics.grids.raw fix: port only if guard missing.
- `5156da67` source-inspection flake: likely obsolete.
- `29a53e0a` OI/DUO/DVO surfaces: current main has no DUO/DVO/OI-grid math; minimal canonical port required; C1/C2 gate.
- `de3a3208` eight-surface Triad tabs: old UI absent from main; joint packet only.
- `88b98fc7` import sort: obsolete standalone.
- `3ed61b5d` round-2 Triad docs: likely obsolete.
- `5e042019` Solstice OI/DUO/DVO grid: Hermes/OpenCode coordination required.
- `d70a7ee5` signal-channel fix: check current alerts diff.
- `9c5734c0` #57 docs: obsolete/superseded.
- `c33e635f` where/how wall read: current main has no wall_response module; minimal conditional behavior only; C1.4 gate.
- `f5316174` Play Walls panel: incompatible as UI port; OpenCode owns visuals.
- `b0de55c6` GEX series: current main lacks gex_series; Hermes schema lease required; C1.5/C5 gate.
- `161384cc` ladder/VWAP/chart/camera/mobile: current main lacks session_vwap; UI belongs to OpenCode; C1.2/C1.3 gate.
- `50119c10` VWAP rename: obsolete standalone.
- `85c32d71` DUO/VWAP/chart correctness: DUO math required; VWAP/chart need current-contract adaptation.
- `958bfc68` DUO vs VEX convention: versioned registry only; C2 gate.
- `4f5fd422` one strong wall + rank: deterministic tie policy only; C1.4 gate.
- `3b2f3d42` ladder magnitude: geometry expectations to OpenCode.
- `a40b2958` ADJ/VOL history: Hermes lease required; C1.5/C5 gate.
- `c3bdf4c1` plain-float Greeks: boundary policy; preserve frozen ML; C1.6 gate.
- `155edeac` ADJ = RAW x |delta| pin: canonical registry already has it; port only missing oracle coverage.
- `bacc9fab` mobile tab CSS: OpenCode visual cleanup.

## C1 status

All six remain claims until current code and independent tests establish them. Old frontend/backend counts are stale without collected node IDs, markers, environment accounting, and same-ignore reconciliation.

## C2 VEX distinction

Current main already distinguishes canonical `VEX_1VOLPT`, display/UI dual scale, and frozen ML single-spot scale. Old factor-15 language is separate history and must not silently rescale current data. Use versioned registry IDs/units and schema migration.

## C3 Triad projection

Current TrinityView has GEX/VEX modes, not old private SurfaceTabs/PlayWalls/PriceLadder/GexChart/heatmapSurfaces files. Define WallDeskSnapshot.v1 jointly. Backend owns aggregation/computation; OpenCode owns rendering/selection. No polarity-by-spot-division, inferred zero-gamma root, fake expiry/zero/stale/ticker defaults, or incompatible-population comparisons.

## C4 metric family

Canonical registry already has raw, delta-weighted, session-volume, and window delta-volume metrics with missing-as-unavailable semantics. Do not relabel session volume gamma as volume-delta-adjusted. Window activity needs comparable cumulative observations, reset/retraction exclusion, and visible interval.

## C5/C6 handoff

Fixture and WallDeskSnapshot.v1 packet are not yet published from this slice. Needed: oracle/serialization/route-projection/history tests that fail on old behavior, fixture hashes, exact commands/results, compatibility effects, source-linked limits. Shared route/server mutations remain under Hermes lease. No merge/deploy/trade, broad rebase, force-push, reset, branch deletion authorized or performed.

## Next command

```sh
git -C /Users/nav/.worktrees/cmd-c0-20260928070352 status --porcelain=v1
git -C /Users/nav/.cline/audit-fixes rev-parse fix/audit-2026-09 origin/main
git -C /Users/nav/.cline/audit-fixes rev-list --left-right --count origin/main...fix/audit-2026-09
```
