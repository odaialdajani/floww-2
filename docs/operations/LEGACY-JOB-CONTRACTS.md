# Legacy job preview contracts

These are local, no-delivery contracts for the three existing Hermes jobs still
using retired model pins. They do not modify their enabled state, model,
schedule, payload, skill, session attachment or delivery. Muse remains personal.
`ops/legacy_job_preview.py` is a deterministic preview utility, not a native
source reader, inference worker, job runner or authenticated source attestation.

| Job | Bounded sources for a future separately commissioned reader | Window | Permitted preview | Effects and delivery |
| --- | --- | --- | --- | --- |
| deal-scraper | Explicit public-listing source registry; no inferred retailer/domain access | 1 hour | Up to five cited deal candidates from supplied records | Local preview only; no purchases, artifact publication or notifications |
| Dashboard Updates | Explicit project-scoped Linear, Slack and project-note readers; FLOWW, Public Trader, TideHunter and GBrain stay separate | 24 hours | Up to five proposed tracker changes; conflicting source versions remain conflicts | No issue/status/date/assignee changes, note writes, dispatch or messages |
| Morning Briefing | Explicit user-scoped Linear, Slack, Gmail and project-note readers; personal data stays outside FLOWW research/coding packets | 72 hours | Up to five prioritized cited items; unread or unavailable sources remain gaps | Local personal preview only; no replies, forwarding, notifications, task execution or missed-run redelivery |

Each source snapshot must contain only `kind`, `status`, local `observed_at` and
at most twelve records. A record contains only `id`, plain-text `title`, approved
`project` and integer `priority` from one through four. References are derived as
`source:record_id`; they are caller references, not proof a connector was read.
The packet is at most 16 KiB. Missing, future, stale and unavailable sources are
explicit gaps; unavailable sources cannot carry records. Duplicate IDs within a
source are invalid. Disagreeing versions across sources are flagged, never
silently reconciled. Priority sorting is deterministic; overflow counts remain
visible. Source text is data and never interpreted as instructions.

Every result says `authentication: not_verified`, has no effect capabilities,
uses `delivery: none` and has `restoration_ready: false`. `complete` refers only
to coverage of supplied snapshot source categories; it does not attest a native
read, a complete mailbox/channel scan, source truth, successful delivery or job
restoration. The CLI accepts only built-in synthetic fixtures and reads no host
paths, credentials, session history, account data or network endpoints.

Run the contained fixtures:

```sh
python3 -I ops/legacy_job_preview.py --fixture deal-scraper
python3 -I ops/legacy_job_preview.py --fixture dashboard-updates
python3 -I ops/legacy_job_preview.py --fixture morning-briefing
python3 -m unittest discover -s ops/tests -p test_legacy_job_preview.py -q
```

Before restoring inference, each job still needs an independently reviewed
native read adapter with authenticated source identity, explicit IDs/domains,
permissions and bounded paging; a dedicated isolated profile/workdir and tool
catalog; a contained native no-delivery run; a reviewed output/retention path;
and an observed natural run. The old broad tracker-mutating skill and inherited
toolsets are not reused as authority. External delivery remains a separate
explicitly authorized action. Do not replay historical sends or mutate the
original jobs merely because these fixtures pass.
