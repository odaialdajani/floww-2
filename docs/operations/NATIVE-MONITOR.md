# Stored-event monitor for native Hermes

Prepared source only. No profile, job, gateway, model, admission or order is activated by this change.

`ops/native_monitor.py` makes at most one GET for each of these fixed stored-read routes:

- `http://127.0.0.1:8213/api/flowseeker/scan-public/observations?ticker=SPY&limit=3&order=received`
- `http://127.0.0.1:8213/api/flowseeker/scan-public/observations?ticker=QQQ&limit=3&order=received`

The existing route reads saved observations without a provider/catalog refresh, scan admission or alert processing (`backend/routes/flowseeker.py:1477`, `backend/services/public_scanner.py:593`). This monitor does not open active databases. It has no arbitrary URL, command, symbol, file-input or credential argument; no redirect, proxy, retry, account, model, order or dispatch capability. Each body is capped at 256 KiB, HTTP timeouts are two seconds, and the two-read sequence has a 4.5-second POSIX main-thread wall deadline. It closes connections and restores its own signal timer afterward. Oversized, compressed, incomplete and malformed responses remain held.

The monitor loads only the existing pure `research_intake.py` compiler. SPY and QQQ are independent units. A valid fresh SPY observation can be emitted with QQQ held, and conversely; each output names eligible symbols and exact held-symbol codes. No eligible symbol means no stdout and a hold. Provider, exact contract, expiry/type/strike and scope must match. Receipt, event, quote, bid and ask clocks must be known, not future and no older than 60 seconds. Output remains research-only and says that Greek/OI clocks and heatmap/orderflow coverage are unverified. It cannot admit an entry or establish profitability.

Source-event IDs bind provider, contract, scope and source clocks; polling times, receipt-only updates and changed values without a new clock do not mint a new event. The output digest is deterministic. `checked_at`, polling ages and the current wall clock are never emitted. Output over 7,000 characters is held before native Hermes could truncate its 8,000-character monitor context.

## Preserved controls and deduplication

Before and after cache reads the production entrypoint checks the existing fleet/role ESTOP files, research PAUSED/control, shared admission schema, parked circuit, unfinished attempts and daily capacity. It never writes these files, removes stops or consumes/reuses an admission ID. Existing held role profiles therefore remain held.

A trusted consumer must maintain this **read-only input** before commissioning:

`~/Library/Application Support/FLOWW/operations/native-monitor/consumed-events.json`

```json
{"schema":"floww-native-consumed-events.v1","source_event_ids":["event_<64 hexadecimal characters>"]}
```

Missing/malformed/symlink controls hold; this code does not create an empty index. All eligible events already consumed means `no_new_source_event`, even if only coverage, receipt or values changed. Native monitor hashing additionally suppresses an identical output within the same job. The trusted caller must atomically reserve the existing shared model budget and record source-event consumption **before** inference. A read-only capacity check is not a reservation. No such caller or scheduler is installed here.

## Local commands and native cron preparation

```sh
/usr/bin/python3 -I ops/native_monitor.py
/bin/bash ops/native_monitor_no_agent.sh
```

Monitor mode returns exit 3 and no stdout on any hold. Native Hermes treats a nonzero monitor source as an early error before inference, including its first tick. Successful empty stdout is not used: native monitor mode would treat its first empty output as a changed baseline. No-agent mode instead returns exit 0, empty stdout and empty stderr on a hold; on eligibility it emits the same research JSON.

After independent source acceptance, install **copies, never symlinks**, of `native_monitor.py`, its existing `research_intake.py` companion and `native_monitor_no_agent.sh` under the existing `floww-research` profile's `scripts/` directory. No configuration, personal context or keys need copying. The shell wrapper is required because native cron takes a script path rather than arbitrary CLI arguments.

Exact prepared commands; neither was executed:

```sh
hermes --profile floww-research cron create '*/5 * * * *' 'Review only the validated stored-event research candidate; no tools, accounts, orders or execution claims.' --name 'FLOWW stored research monitor' --monitor-script native_monitor.py --interpreter /usr/bin/python3 --model minimaxai/minimax-m3.1-flash --provider nvidia --reasoning-effort max --repeat 1 --deliver local --failure-deliver local --catch-up off --timezone America/New_York --grace-minutes 0 --paused --paused-reason 'Prepared only; shared reservation and consumed-event owner not commissioned'
hermes --profile floww-research cron create '*/5 * * * *' --name 'FLOWW model-free stored event receipt' --script native_monitor_no_agent.sh --no-agent --repeat 1 --deliver local --failure-deliver local --catch-up off --timezone America/New_York --grace-minutes 0 --paused --paused-reason 'Prepared only; controls remain held'
```

Do not resume the model-backed recipe as a substitute for shared budget admission. The second recipe performs zero model calls by native contract. `--no-agent` and `--monitor-script` are mutually incompatible. Native scripts must resolve inside their owning profile's `scripts/`; these templates use only that supported layout. Native CLI flags and first-tick semantics were checked against installed Hermes source `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` (`hermes_cli/subcommands/cron.py`, `cron/monitor.py`, `cron/scheduler_script.py`, `cron/scheduler.py`).

## Verification

Run the new monitor tests and the existing pure intake checks, with no live network/model calls:

```sh
/usr/bin/python3 -m unittest discover -s ops/tests -p test_native_monitor.py
/usr/bin/python3 -m unittest discover -s ops/tests -p test_research_intake.py
ruff check ops/native_monitor.py ops/tests/test_native_monitor.py
```

Tests cover fresh/mixed/missing/stale/future/conflicting evidence, stable receipt-independent IDs, consumed events, malformed JSON, fixed GETs, independent HTTP failures, body/deadline caps, preserved control bytes, symlink rejection, output caps and stop/circuit changes during reads. Source tests do not establish a commissioned native job, fresh market coverage, a Liquid binding, orders or a profitable strategy.
