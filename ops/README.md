# FLOWW local observer

This model-free observer records local transport health and pinned release identity. It has no repair, restart, provider, model, account, research, order or Liquid capability. A healthy result proves only the three checks below, not chart behavior, market freshness, product acceptance or profitability.

Each `check once` makes at most one GET to each fixed address, without proxies, redirects, credentials or fallback:

- `http://127.0.0.1:8213/api/version`
- `http://127.0.0.1:8213/health`
- `http://127.0.0.1:3000/`

Each GET runs in an isolated Python child with a **2-second wall timeout**, including the child startup. A timed-out child is killed and reaped. Three sequential probes take up to roughly six seconds plus process/state overhead. Each accepted body is at most **256 KiB**; an extra guard byte detects an oversized response. Compressed bodies are refused, and a declared Content-Length must match the complete received body. Nothing retries, follows a redirect, spends a provider/model budget or enables execution. Response bodies are discarded after extracting bounded health/revision metadata or an HTML digest.

The observer reads only `~/Library/Application Support/FLOWW/local/runtime.json` and the pinned release's `frontend/build/index.html` for identity. The release must remain inside the local `releases` directory and its directory name must match the recorded 40-character SHA prefix. Store/journal paths in runtime metadata are ignored; active databases are never opened. Backend SHA prefixes of 7–40 hex characters must match the pin, and frontend HTML SHA-256 must equal the pinned compiled HTML. A pin change during collection yields unknown. Missing or malformed evidence stays unknown; definite HTTP/transport failure or a revision/digest mismatch is unhealthy.

## Commands

Python 3.9 or newer, standard library only, on macOS/POSIX with `fcntl`:

```sh
/usr/bin/python3 -I ops/watchdog.py check once
/usr/bin/python3 -I ops/watchdog.py status
/usr/bin/python3 -I ops/watchdog.py pause
/usr/bin/python3 -I ops/watchdog.py resume
```

Default state: `~/Library/Application Support/FLOWW/operations`. An explicit `--state-dir /private/path` before the command changes only the observer's state location, never its network targets or release pin. State directories use mode 0700, files 0600; symlink state directories are refused. `status` reads saved state and does not collect or create a sample.

`pause` atomically publishes a `STOP` sentinel before waiting for any collector. It prevents new probes; children also check before opening/requesting/reading the body. A read already in flight can finish within its two-second deadline, and no next probe starts. Creating `STOP` manually also pauses. `resume` takes the collection lease, removes the sentinel and returns the existing sample; it does **not** make network calls or imply a new healthy sample. If the latest sample was paused, the result is unknown until the next check. Concurrent collection returns busy without overwriting the owning process's sample.

| Exit | Meaning |
|---:|---|
| 0 | Fresh healthy transport and matched pin |
| 1 | Fresh unhealthy transport or identity mismatch |
| 2 | Unknown/missing/malformed evidence, future clock, or observer state error |
| 3 | Paused (also the successful `pause` command's intentional exit) |
| 4 | Another collector owns the lease; no new collection |
| 5 | Saved sample older than 600 seconds, regardless of its former state |

Every status includes explicit `freshness` and sample age when known. A previous green sample does not remain fresh indefinitely. `desired_state` distinguishes the current pause marker from the most recent sample's result. Execution and Liquid capabilities are explicitly false in output.

## Durable state and retention

A nonblocking `fcntl.flock` excludes overlapping collectors on this host. The kernel releases ownership when a process exits; no stale PID file needs force removal. Snapshot/status writes use private staging files, fsync and atomic replacement. Retention is at most 288 generated snapshots, plus `status.json` and a two-file event journal (`events.jsonl`, `events.1.jsonl`), each journal at most 256 KiB. No unbounded launchd log file is required. The lock and STOP marker are control state, not trading instructions or a general worker queue.

## Scheduling

`com.floww.operations-watchdog.plist` is a reviewable **template**, not installed by these files. It uses `StartInterval=300`, `RunAtLoad=false`, and no `KeepAlive`; a nonzero health result cannot cause a restart storm. It runs only this observer and sends stdout/stderr to `/dev/null`; durable status/events carry its results. Review the absolute interpreter/script paths before installing. The template runs a hash-verified copy at `~/Library/Application Support/FLOWW/operations/runtime/watchdog.py`, outside the Documents background-access boundary. The integrator must preserve a source/runtime hash manifest with the deployment receipt.

The existing Hermes `confluence-decoder-health-check` remains unchanged. That job has its own health/recovery purpose. This separate observer checks release identity and durable sample freshness independently of Hermes and never attempts a second restart or repair loop. Do not add another schedule for this same observer when installing the template.

Installation, activation and any deployment receipt belong to the root integrator. Tests and a template do not prove the observer is loaded or running under launchd.

## Verification

```sh
/usr/bin/python3 -I -m unittest discover -s ops/tests -v
```

Tests use temporary files, mocked HTTP transports and local child-process fixtures only. They cover matching/mismatched/unknown identity, redirected or oversized bodies, hard child timeout and reaping, pause during collection, resumed stale status, competing processes, private state and bounded retention. They do not contact the active app, provider or database. No backend/frontend suite is needed for this independent standard-library directory; its tests make no application acceptance claim.


## Saved research intake

`research_intake.py` is a separate pure module with no I/O, model or execution capability. `compile_snapshot(saved_input, decision_time)` consumes a bounded saved-observation page at an explicit decision time. `validate_research(packet, response)` accepts only closed, cited copies of supplied fields and units. Inputs to the compiler must come from the trusted saved-data intake; the packet digest is content identity, not authentication of a provider.

The result is always `review_only`, `executable=false` and `internal_research`. Stale historical facts can be copied with their old clocks; unknown clocks, sizes, currency and contract multiplier stay unknown. Future observations, clocks after receipt, conflicting duplicate events, changed numeric values, invented citations and confidence/execution/venue claims are refused. Polling metadata cannot mint a fresh source event. Packet IDs bind a decision-time analysis; use observation/source identity rather than a new polling/decision packet ID when designing later deduplication.

This is an evidence-copy gate, not an autonomous research strategy or a trusted execution admission service. A validated copied fact does not establish its provider authenticity, market freshness, predictive value or a permissible fill. Native worker dispatch and Liquid Paper remain separately gated. See `docs/operations/AUTONOMY-SPEC.md` and the linked implementation plan for the full contract.
