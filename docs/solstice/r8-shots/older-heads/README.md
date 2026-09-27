# Older-head captures — NOT evidence for the current build

These five images were captured at an earlier head (the previous R8 receipts
pinned `36872db7`). They are kept here, moved out of the parent directory on
2026-09-27, for two reasons:

1. `RECONCILIATION.md` cites `prod-gex.png` and `prod-vex.png` as the live-pixel
   verification for PR #50 (R8 UI blend). Deleting them would break that trail.
2. They show real rendered states and are useful when diagnosing a visual
   regression against the blend pass.

**They do not evidence the current build.** Do not cite them for any acceptance
claim. The current-head captures are in the parent directory, indexed by
`../SHOTS.md`, and their authority is `../../R8-ACCEPTANCE.md`.

| File | Was |
|---|---|
| `solstice-desktop.png` | Solstice single grid, live SPY chain |
| `prod-gex.png` | Production stack, GEX tab (PR #50 blend verification) |
| `prod-vex.png` | Production stack, VEX tab (PR #50 blend verification) |
| `movers-populated.png` | Top Movers populated live |
| `blend-inspector.png` | Inspector blend pass |
