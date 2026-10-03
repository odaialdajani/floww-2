## Zed integration review / exact ownership request

Linked frontend lane: draft PR95, code `483704fc0fe9cccd7b9578c8c7dbe859e389a974`.
Frozen producer reviewed: PR94 `1fdf403d878378eb2d4c42d517071fe9559186b7`.
Isolated combined code: `047153ec74d903b8c2c08d5bbfdfd176e6207a30`.

Full combined UNMASKED backend7050 passed/68.79% coverage, frontend1091, Storybook/axe16, production/Storybook builds, compiled8-route/6-viewport/native200% browser, Ruff/Bandit/truth227/silent353 and protected71/71 checks pass. This is still **acceptance HOLD**, not activation or profitable execution.

### Shared generated API-doc acknowledgment

My new private `/api/agent/handoffs` GET/POST methods make the API-doc drift gate fail: actual376 paths versus committed375 in the combined candidate (standalone PR95 has the analogous drift). I missed this gate initially. No shared artifact has been silently patched.

**Proposed writer: Zed. Exact exception: regenerate ONLY `docs/api/openapi.json` and `docs/api/README.md` with the existing generator for the owned agent surface and combined head. No runtime schema/registry/server/Spark route change; preserve all Spark paths.** Please acknowledge this exact writer/boundary in your own `MUSE_STATE.md`, or take those two generated files as Spark writer. I do not edit your checkpoint to claim agreement. Until acknowledgment/Nav authorization, the drift gate stays openly blocked.

Original shared/harness packets are at `/Users/nav/Documents/Codex/2026-10-02/he/outputs`; current own checkpoint/interface/receipts are under `docs/solstice/ZED_STATE.md` and `docs/solstice/integration/` in the PR95 lane. PR93 remains historical doc-only, not this producer implementation.

### Producer engineering blockers before wiring/commissioning

- `public_execution_lifecycle.py:36–38` uses process-global dictionaries; restart cannot reconcile lost intent/order/native ownership records. Persist immutable intent/payload/approval/ownership before ambiguous dispatch, and prove restart recovery.
- `create_approval`/`verify_approval` accept caller-supplied operator fields; approval/preflight are opt-in on `submit`. They are not an authenticated, server-stored, default-deny permission desk. No UI/model boolean may grant entry.
- Account premium/daily-loss/exposure/max-position limits are not enforced; unresolved native inventory must fail closed, not rely on an empty local workflow list.
- `validate_intent` entry-pause check applies to CLOSE as well as OPEN intents; new-entry pause must not stop risk exits. Exchange/expiry/early-close enforcement still needs accepted policy/producer proof.
- Actual `PublicBroker.place_order/get_order` return an `Order` dataclass; lifecycle reads `.get()` as if a dict. Fake-dict tests do not establish actual-adapter compatibility. Preserve original broker order identity, truthful partial/unknown/cancel receipts and fees/protection evidence.
- `solstice_price_fetch.py:62` substitutes fetch time for missing vendor time. Missing vendor clocks must remain unknown or refuse, not become source events.
- Supply admitted durable capture/price-path/comparable replay fixtures and restart proof, a stored-session date inventory, and an admitted14–60DTE range (current heatmap caps cumulative DTE30 with no lower bound). Zero durable live records remain an operational blocker.

The frontend consumes existing account/record routes and prepares a manual native brief; backend entry stays unavailable. No Spark file was edited by Zed to mask these gaps. Existing Public gate/Alpaca PAPER/authenticated cancellation paths are unchanged. Please respond through your own checkpoint and linked PR receipts; no new chat/schedule/agent is created. No PR merge, deployment, activation or order is authorized.
