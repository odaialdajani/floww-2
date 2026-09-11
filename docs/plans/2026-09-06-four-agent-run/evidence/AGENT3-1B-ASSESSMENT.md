# Agent 3 backlog — 1b assessment: alert_engine rule catalog (live vs dead code)

## Method
Read `backend/alert_engine.py` `detect_alerts()` (the production detection
method) and `ALERT_TYPE_CATALOG` (the metadata table). For each catalog rule,
report: (a) does `detect_alerts` actually fire it, (b) which pipeline(s)
produce it, (c) whether the frontend has any UI rendering for it on main.

## Rules in ALERT_TYPE_CATALOG (11 entries)

| Rule | Priority | Fired by detect_alerts? | Pipeline(s) | Frontend rendering on main? |
|---|---|---|---|---|
| GAMMA_FLIP | HIGH | YES — regime change (line 158) | alert_engine + exposure_alerts (gamma_flip_approach→RULE_GAMMA_FLIP) | NO (this branch wires it) |
| GAMMA_SQUEEZE | HIGH | YES — negative gamma + flip proximity + gex spike (line 177) | alert_engine | NO |
| MOMENTUM_EXTREME | HIGH | YES — score > 80 or < 20 (lines 191, 199) | alert_engine | NO |
| WALL_BREACH | MEDIUM | YES — call/put wall cross (lines 212, 224) | alert_engine | NO |
| GEX_MAGNITUDE_SHIFT | MEDIUM | YES — total GEX change > 40% (line 236) | alert_engine | NO |
| GAMMA_FLIP_PROXIMITY | MEDIUM | YES — within 0.3% of flip, no GAMMA_FLIP already fired (line 252) | alert_engine | NO (distinct from GAMMA_FLIP; do NOT conflate) |
| PIN_RISK | LOW | YES — within 0.2% of max gamma strike (line 263) | alert_engine | NO (distinct from CHARM_PIN; do NOT conflate) |
| CHARM_PINNING | HIGH | YES — _detect_charm_pinning (line 383) | alert_engine | NO (0DTE charm; distinct from exposure CHARM_PIN; do NOT conflate) |
| VANNA_REGIME_CHANGE | HIGH | YES — _detect_vanna_regime_change (line 404) | alert_engine | NO |
| UNUSUAL_PC_OI_RATIO | MEDIUM | YES — put/call OI ratio > 2x (line 424) | alert_engine | NO |
| MAX_PAIN_MAGNET | LOW | YES — within 1% of max pain in positive gamma (line 440) | alert_engine | NO |
| VOLUME_SPIKE | MEDIUM | YES — real contract volume 3x at near-ATM (line 293) | alert_engine | NO |
| CLUSTER | MEDIUM | YES — laddered accumulation, 3+ legs same side (flow_alerts line 836) | flow_alerts (per-ticker cluster scan) | NO |

(Note: CLUSTER is a live producer in `flow_alerts.py`, not dead code.)## Findings

### All 11 catalog rules are live producers
Every rule in `ALERT_TYPE_CATALOG` is actually fired by `detect_alerts()` —
there is no dead code in the catalog. Each has a real detection branch with
thresholds and an `Alert(type=...)` emission.

### Two distinct GAMMA_FLIP pipelines
- `alert_engine.py` line 158: fires `type="GAMMA_FLIP"` on regime change
  (positive→negative or negative→positive gamma). This is the regime-change
  signal.
- `exposure_alerts.py` line 317: maps `gamma_flip_approach` event kind →
  `RULE_GAMMA_FLIP`. This is the proximity/approach signal.

The frontend badge maps both to the same `GAMMA_FLIP` rule kind via
`exposureBadgeFor()`. The badge title currently says "Gamma regime change —
dealer gamma flipped from positive to negative" — that describes the
alert_engine regime-change signal correctly. The exposure_alerts proximity
signal would be mislabeled by this title (it's "price pressing dealer flip
level," not "regime already flipped"). This is a known limitation: one badge
label for two distinct producer semantics. Leaving as-is per unit 1a scope;
proper fix (separate rule kinds or producer-aware labels) is future work.

### Three conflation traps (do NOT wire these as if they were the exposure
badges already done)

1. **CHARM_PIN (exposure) ≠ CHARM_PINNING (alert_engine 0DTE)**
   - exposure_alerts.py: `RULE_CHARM_PIN = "CHARM_PIN"`, fired from
     `charm_pin_formed`/`charm_pin_shifted` event kinds (line 323)
   - alert_engine.py: `type="CHARM_PINNING"`, 0DTE charm-driven pinning
     (line 383, `ALERT_TYPE_CATALOG` entry line 89)
   - These are DIFFERENT signals from DIFFERENT pipelines. The frontend
     already has a `CHARM_PIN` badge (unit 1a). Do NOT add a `CHARM_PINNING`
     badge under the same name or in the same module without an explicit
     design decision.

2. **GAMMA_FLIP (exposure/alert_engine regime) ≠ GAMMA_FLIP_PROXIMITY
   (alert_engine proximity)**
   - `GAMMA_FLIP` = regime change (alert_engine line 158) + proximity approach
     (exposure_alerts line 317)
   - `GAMMA_FLIP_PROXIMITY` = spot within 0.3% of flip, only if no GAMMA_FLIP
     already fired (alert_engine line 252, `ALERT_TYPE_CATALOG` entry line 87)
   - Different alert kinds, different semantics. Do NOT map
     `GAMMA_FLIP_PROXIMITY` to the existing `GAMMA_FLIP` badge.

3. **PIN_RISK (alert_engine) ≠ anything in exposure_alerts**
   - `PIN_RISK` = spot near max gamma strike (alert_engine line 88, 263)
   - No `RULE_PIN_RISK` exists in exposure_alerts.py. The exposure pipeline
     has no pin-risk producer. Do NOT invent one.

### No dead code found
No catalog rule is unfired. No detection branch is stubbed out. The
`ALERT_TYPE_CATALOG` is in sync with `detect_alerts()` for all 11 entries.

### Frontend rendering gap
Zero of these 11 rules (plus the 5 exposure rules already wired in unit 1a)
have any frontend badge rendering on main `56cfff2`. Unit 1a closed the gap
for TOXIC_FLOW, GAMMA_FLIP, VEX_WALL, CHARM_PIN, LIQUIDITY_STRESS. The
remaining 11 alert_engine rules + GAMMA_FLIP_PROXIMITY are still unrendered.

## Recommendation for unit 1c (future)
Wire the remaining alert_engine rules to a second badge module (e.g.
`alertEngineBadges.js`) that maps `ALERT_TYPE_CATALOG` type strings → badge
descriptors, distinct from `exposureBadges.js`. Each rule needs its own
heuristic label and its own RED test. Do NOT fold them into
`exposureBadges.js` — the two pipelines have different producer semantics and
the conflation traps above are real bugs waiting to happen.

## Assessment complete
All 11 alert_engine catalog rules + CLUSTER in flow_alerts are live producers.
No dead code. No rules to report as dead. The rendering gap is real and large
(11 alert_engine rules + GAMMA_FLIP_PROXIMITY proximity variant + CLUSTER
still unrendered). Unit 1b assessment complete; unit 1c (wire remaining
rules) is a separate future unit requiring its own Agent-1 admission.
