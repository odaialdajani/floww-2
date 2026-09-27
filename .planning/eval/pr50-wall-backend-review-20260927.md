# Independent wall reading backend review - 2026-09-27

Final verdict: PASS for the focused backend wall-reading changes after independently verifying the corrections below. Initial verdict was CHANGES REQUIRED for two findings. Review is read-only for tracked source. No network, provider, model or trading calls. Probe subprocesses were hidden; their socket connects were explicitly blocked.

## Demonstrated improvements

The new wall-local session-volume branch runs before open-interest/delta checks. Independent pure-function probes verified positive volume with zero or absent open interest still produces the expected 500 exposure and one usable/positive-volume row. Numeric volume zero now has one usable row and no missing rows; absent volume has zero usable and one missing row. Valid zero delta and zero gamma preserve measured-zero contribution. `volume_n` remains the positive-volume row count while `volume_usable` counts valid nonnegative observations. Existing delta usable/missing semantics stay separate.

The live response assembly now copies real per-strike contract gross from the VEX producer, which accumulates absolute contributions before cancellation. This is the correct source; summing absolute already-netted cells would be wrong.

## Findings

1. **Boolean volume incorrectly establishes usable data.** `float(False)` becomes zero and `float(True)` becomes one. The new coverage field counts those malformed booleans as valid reported volume, so False can falsely prove measured zero. Explicitly reject booleans and cover both values in the focused tests.
2. **Stored snapshots drop the new gross and source metadata.** `heatmap_history._full_grids` copies named cell dictionaries but not `vex_strike_gross` or `vex_meta`. A direct snapshot extraction probe retains the signed cell but loses both fields, so replay cannot preserve the new true-gross reading and its basis. Preserve these source fields in the stored grid representation and verify actual record/reopen hydration, with old snapshots honestly unavailable when the fields were never captured.

Evidence: `output/pr50-wall-backend-initial-probe.json` contains the actual producer outputs for numeric zero, absence, both booleans, zero/missing open interest, zero delta, zero gamma and the snapshot field-loss checks. The probe used only new development inputs and pure local transformations. No broad test suite was run.

## Independent sibling sweep - 01:06 UTC

Boolean coercion is also present in pre-existing shared input helpers. Pure local calls demonstrate `gamma=False` makes both `volume_usable=1` and `daddex_usable=1` at measured zero; `delta=False` makes `daddex_usable=1` at measured zero. Boolean `oi=True` and `multiplier=True` are accepted numerically. These shared-helper behaviors predate the patch but bound its invalid-input guarantees; the gamma case directly affects the newly added volume coverage. Reported to the owner for a focused wall-local correction or an explicit remaining limitation.

Evidence: `output/pr50-wall-backend-sibling-probe.json` retains all seven inputs/results and SHA-256 values for the three reviewed source files. Network connections were blocked. This probe does not demonstrate provider ingestion of boolean inputs; it demonstrates the local public calculation accepts them.


## Final independent verification - 01:11 UTC

Both initial findings and the directly related boolean sibling cases are corrected. Independent probes against the final production source passed all 14 boolean cases across volume, gamma, delta, OI and three multiplier aliases. Reported numeric zero retains coverage; absent volume does not; positive session volume remains 500 with zero, missing, malformed or negative OI and missing delta. This verifies the intended independence.

An independent local DuckDB file was created, a development snapshot written, the connection closed, and the file reopened read-only. The stored/replayed actual fields preserved per-strike gross, source metadata and wall coverage exactly. This independent storage probe uses an explicit gross 731.25 and net cell zero to detect accidental reconstruction from net. Old snapshot extraction leaves missing gross/source fields absent instead of inventing them. Temporary data was removed on completion; no application data was used.

Evidence: `output/pr50-wall-backend-final-probe.json` retains the fourteen case outputs, reopened grid and final SHA-256 values:

- exposure_metrics.py: `0e32379658cf2c6cb2dbe77a21751fc4ce8c05377a34013fb4cb1423db3a2d88`
- server.py: `54be26a01b824c30bef472bca673f9421f0d4056837e5af9da8c32b8d3167681`
- heatmap_history.py: `f1e1e25b73a6cd1e3c8e688b03b0011741f59a5e9557a341f9921e6aba3c6fd8`

Source inspection confirms `_with_vex` directly preserves producer contract gross, `_full_grids` stores the two extra fields with type checks, and nonfinite accumulated wall totals return None instead of a non-JSON finite-number claim. The root separately reports 40 focused tests passing; this review's independent execution is the pure-input and real local storage probes above, not a repeat of that full test run. No provider/model calls, paper changes, live trading, server restart, or browser display verification were performed by this review. No remaining blocker was found in the reviewed backend scope.
