# Paper settings independent frontend review - 2026-09-26

Scope: local draft PaperSettings.jsx/test, surgical SettingsPanel.jsx mount, and accepted accounting decision in docs/adr/0010-paper-accounting-proposed.md. No active backend paper work, research metrics or unrelated source changed. This is not complete paper-account setup or activation. All test subprocesses were hidden with explicit Node argument arrays/windowsHide:true; no provider, model, broker, browser window or external call.

## Findings

Recheck at 2026-09-26 22:37 UTC: both findings below are CLOSED for the tested local draft UI. Original failure evidence is retained below as history. All six independent mounted probes pass, including the original three failing cases, off-state retention, a complete valid draft save/remount, cleaning an unselected cached account draft, and whitespace identity rejection. The two existing suites also pass all twelve tests. This closure does not establish account creation, server-side settings, account ownership, activation, economic accounting correctness, or trading authorization.

### 1. Invalid stored slippage choices can be silently resaved (medium)

Status: CLOSED. Hydration now rebuilds every stored draft from known typed fields, clears malformed slippage choices without selecting defaults, and save verifies draft shape/choices again. The original two corruption probes now pass. Independent extra coverage confirms inactive cached drafts are cleaned and unknown fields removed.

readSetup accepts the entire drafts object without validating its fields. Save validates only dollar strings. A stored new-account draft with slippageEnabled=on/slippageMethod=both or slippageEnabled=enabled/slippageMethod=cash is loaded and then saved successfully. The select cannot show the invalid value, so the display can appear unchosen while the underlying invalid choice remains saved. This violates the local draft choice contract; it does not prove actual double charging because no execution path is wired here.

Reproduced with two mounted scratch cases, both FAIL against expected reject-or-clear behavior. Seed localStorage with version1/accountChoice=new and either malformed enum pair, mount actual PaperSettings, click Save paper setup, inspect stored JSON and status. Both values survive with successful-save status.

Minimal correction: validate/sanitize known draft fields and enum values on storage hydration, including every persisted draft; only allow empty/on/off and empty/price/cash. Validate again on save. Empty choices remain allowed for an explicitly incomplete local draft; do not silently choose a mode or method. Reject malformed draft shape/name/value types without treating a browser cache as account authority.

### 2. Empty eligible account identity bypasses explicit account selection (medium)

Status: CLOSED. Eligible identities must be nonempty strings without whitespace; invalid cached account keys and selected identities are discarded. The original empty-identity probe and an added whitespace-identity check pass without successful-save status or implicit selection.

The account filter accepts any string id including the empty string. Default selectedAccount is empty. With accounts=[{id:'',name:'Malformed account',paper:true,venue:'internal'}], choosing Use a saved paper account yields accountKey='account:' even though the picker still has its empty selection. Save reports success without the user selecting an account. Mounted scratch assertion FAILS.

Minimal correction: require a nonempty valid account identity (and reject whitespace-only identity), and require a nonempty selectedAccount before matching. Do not silently pick an account. Caller must still supply ownership-verified accounts at future integration; this local UI cannot establish ownership itself.

## Evidence

- Existing PaperSettings and SettingsPanel suites independently rerun:2suites/7tests PASS, exit0. Log output/paper-settings-review-20260926/existing-tests.log.
- Independent mounted scratch suite:3FAIL/1PASS, exit1. Two enum failures and one empty-account failure as above. Positive case proves off retains method plus price difference across save/remount, and switching new to existing does not inherit the new-account draft. Test and log: output/paper-settings-review-20260926/paper-settings-independent.test.jsx and independent.log.
- SettingsPanel diff is only the PaperSettings import and mount within existing settings content. It passes no accounts, so the current actual surface honestly reports no saved accounts. No backend creation/settings/update/activation call exists in this component.
- No capital or risk default is inserted; blanks deliberately remain drafts. On/off and one method select are separate. Native inputs/selects/buttons have associated labels; save status/error use status/alert roles; unavailable controls use a disabled fieldset. This is a basic semantic accessibility inspection, not a physical keyboard or screen-reader certification.
- Statement that changes affect future paper trades is a future accounting rule only; the current save message explicitly says device-local and no account/trade creation. Existing-account configuration still needs ownership/settings integration and backend validation.

## Tested hashes

- frontend/src/agent/PaperSettings.jsx = 755e793bad7f7f8140b607a76a2054c94239b46515b52d87c8ffd4dc0d2dcdcb
- frontend/src/agent/PaperSettings.test.jsx = fab1be881efd12a051ce01d8871f53e0771786faa2ee0490a4ce12db5ffb71fb
- frontend/src/components/SettingsPanel.jsx = 75c51f195b592a35b3e4fb9f2acce288f6b57b20aa5bc402b27a7f33be3f3e77
- docs/adr/0010-paper-accounting-proposed.md = 67c6011dd5d9eb8081ec4e9efb0f8095dfacfb59e4d4442c2de1e6bb64ffe40d

Manifest output/paper-settings-review-20260926/source-hashes.json. Future author corrections must be retested against new hashes. All owned test processes completed. No production build/browser run by reviewer; no claim of complete paper setup, economic accounting validation, release acceptance or trading authorization.

## Recheck evidence and exact hashes

- Independent mounted probes: 1 suite / 6 tests PASS, exit 0. Log: output/paper-settings-review-20260926/independent-recheck.log. Original test cases preserved and two additional valid/cache cases added in the same scratch test file.
- Existing PaperSettings and SettingsPanel tests: 2 suites / 12 tests PASS, exit 0. Log: output/paper-settings-review-20260926/existing-tests-recheck.log.
- frontend/src/agent/PaperSettings.jsx = 856122c69d138969bfad6ad070956f3dc631c0d42cc85087d0f2a4053f818a70
- frontend/src/agent/PaperSettings.test.jsx = 6360afc21c67b4d809aa53d63304ef13e8fc921a36c9d6c2b346c520d7ca2481
- frontend/src/components/SettingsPanel.jsx = 75c51f195b592a35b3e4fb9f2acce288f6b57b20aa5bc402b27a7f33be3f3e77
- docs/adr/0010-paper-accounting-proposed.md = 67c6011dd5d9eb8081ec4e9efb0f8095dfacfb59e4d4442c2de1e6bb64ffe40d

Manifest: output/paper-settings-review-20260926/source-hashes-recheck.json. Reviewer changed only this report and its scratch evidence; production sources were read-only. All owned test subprocesses completed with windowsHide:true. Full frontend build remains with parent review and is not claimed here. No remaining blocker found in this narrowly scoped local-draft recheck.
