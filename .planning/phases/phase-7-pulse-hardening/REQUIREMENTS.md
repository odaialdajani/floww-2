# Phase 7 — REQUIREMENTS (Pulse Hardening)

Parent: PLAN.md (same dir). Each requirement traces to a ticket.

| Req | Text | Ticket | Acceptance |
|---|---|---|---|
| R7.1 | Cold-start sessions enforce post-tightening gates (92/$25M/6σ) with no user interaction | 7.1 | Fresh-profile mount: SCORE fires at 92; Jest parity assert engine defaults == DEFAULT_RULES |
| R7.2 | 0DTE lotto (score 70-84, low vol/OI) never fires | 7.2 | Jest: synthetic 0DTE low-mult row suppressed; genuine size still passes via WHALE/SCORE |
| R7.3 | Put-ASK rows keep reference BULLISH signal AND carry visible hedge-ambiguity tag | 7.3 | Jest: flag present on put-ASK, absent on call-ASK; tooltip explains |
| R7.4 | Pulse surfaces read Solstice-native (tokens, radius, mono) | 7.4 | Token diff clean vs index.css :root; side-by-side screenshot sign-off |
| R7.5 | Reference chrome present: refresh/pause, HOW TO READ, info tooltips, per-row 90s subline | 7.5 | Mount test asserts presence; checklist against ui_spec.md |
| R7.6 | One money formatter, one DTE calculator, one clock (scanLogic) | 7.6 | Zero local fmt/dte helpers in Blademap; all call sites use scanLogic |
| R7.7 | No two gates disagree on WHALE; no stale-85 pref path | 7.7 | Badge tests updated; slider/rule/drift paths removed or unified |
| R7.8 | No unreachable views ship (VOL, Academy) | 7.8 | grep setTab shows only live targets; bundle contains no drawVol |
| R7.9 | Every panel has loading/empty/stale/error/unavailable states; fetch-failure ≠ filter-empty | 7.9 | Endpoint-blocking walkthrough with screenshots per state |
| R7.10 | InstitutionalAlertsPanel cluster fate decided by Nav | 7.10 | checkpoint:decision recorded; mount or delete executed accordingly |

Non-requirements: backend threshold writes; auto-tuning; ROADMAP edits.
