# Project Oracle — Operations Runbook

## Quick Start

### Start the observability stack

```bash
cd /Users/nav/Documents/GitHub/floww
docker compose -f docker-compose.observability.yml up -d
```

This starts:
- **Prometheus** — http://localhost:9090 (metrics storage + alerting)
- **Alertmanager** — http://localhost:9093 (alert routing to webhooks)
- **Grafana** — http://localhost:3001 (dashboards, admin/admin)
  (host 3001, not 3000: `docker-compose.yml` already publishes the dev frontend
  on 3000, and this stack is meant to run alongside it)

### Verify the stack is healthy

```bash
# Prometheus targets
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep -E "health|labels"

# Floww metrics endpoint
curl -s http://localhost:8000/metrics | head -20

# Grafana health (host 3001 -> container 3000)
curl -s http://localhost:3001/api/health
```

### Access Grafana

1. Open http://localhost:3001
2. Login: `admin` / `admin` (change recommended)
3. Dashboards are auto-provisioned:
   - **Project Oracle — Live Metrics** (uid: `oracle-live`) — Real-time metrics
   - **Project Oracle — SLA** (uid: `oracle-sla`) — Uptime, latency, error budgets
   - **Project Oracle — Cost** (uid: `oracle-cost`) — Spend tracking, budget burn

---

## Durable research storage (DUCKDB_PATH)

The heatmap/research history lives in DuckDB. **By default it is in-memory**
(`DUCKDB_PATH` unset -> `:memory:`), which means:

* every backend restart loses recorded wall history, and
* the API reports `durable: false` rather than pretending the data is saved.

That is deliberate and honest — `server.py` only reports a wall as durable when
the recorder is actually file-backed, so nothing claims a save that did not
happen. To make history survive a restart, point it at a file:

```bash
# in your backend environment
export DUCKDB_PATH=./data/floww.duckdb
```

`duckdb_engine.py:545` reads it and falls back to `:memory:` with a logged
warning if the path is unusable, so a bad value can never block startup.

This variable is currently read by `backend/services/duckdb_engine.py` and
`backend/server.py` and is set by NO file in the repository — there is no
`.env.example`, so it must be set by hand or in your deployment environment.

---

## Alert Reference

### Alert Rules

| Alert | Severity | Condition | First Response |
|:------|:---------|:----------|:---------------|
| `IngestionStalled` | WARNING | No messages for 5min during market hours | Check the Public.com feed and `ingestion_pipeline` (there is no Schwab WebSocket — Schwab is retired) |
| `QueueBackpressure` | CRITICAL | DuckDB queue > 9000 for 1min | Check DuckDB writer thread; may need to restart `duckdb_engine` |
| `AnomalyDetected` | CRITICAL | Anomaly threshold breached in last 60s | Check VPIN/QI z-score; review flow toxicity |
| `APIErrorRateHigh` | CRITICAL | 5xx rate > 0.1/s for 5min | Check server logs; may need to restart `server.py` |
| `Budget80Percent` | WARNING | Any cost metric > 80% of budget | Review spend in Cost dashboard; consider throttling |
| `Budget95Percent` | CRITICAL | Any cost metric > 95% of budget | **Phone alert fires** — immediately review and pause non-essential spend |

### Silencing an Alert

**Temporary silence (Grafana):**
1. Open Grafana → Alerting → Silences
2. Create silence with matchers for the alert name
3. Set duration (e.g., 1h for planned maintenance)

**Via Alertmanager API:**
```bash
# Silence IngestionStalled for 1 hour
curl -X POST http://localhost:9093/api/v2/silences \
  -H 'Content-Type: application/json' \
  -d '{
    "matchers": [{"name": "alertname", "value": "IngestionStalled", "isRegex": false}],
    "startsAt": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
    "endsAt": "'"$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)"'",
    "createdBy": "ops",
    "comment": "Planned maintenance"
  }'
```

**Acknowledge via API (clears dedup cache):**
```bash
curl -X POST http://localhost:8000/api/alerts/acknowledge \
  -H 'Content-Type: application/json' \
  -d '{"alert_id": "AnomalyDetected", "resolved": true}'
```

---

## Phone Alerting (Twilio)

### Configuration

Set these environment variables in `backend/.env`:
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+15551234567
NAV_PHONE_NUMBER=+15559876543
```

### Behavior

- **CRITICAL** alerts → SMS + voice call
- **WARNING** alerts → SMS only
- **LOW** alerts → Dashboard only (no phone)
- **Quiet hours**: 22:00–06:00 ET (no calls unless emergency)
- **Market hours override**: 09:30–16:00 ET weekdays always allow calls
- **Emergency bypass**: `AnomalyDetected`, `QueueBackpressure`, `APIErrorRateHigh` always fire
- **Deduplication**: 15-minute cooldown per unique alert ID

### Test the dispatcher

```bash
# Trigger a test critical alert
curl -X POST http://localhost:8000/api/alerts/fire \
  -H 'Content-Type: application/json' \
  -d '{
    "alert_id": "TEST-001",
    "severity": "CRITICAL",
    "title": "Test Alert",
    "message": "This is a test — ignore",
    "category": "AnomalyDetected"
  }'
```

### Check dispatcher status

```bash
curl -s http://localhost:8000/api/alerts/status | python3 -m json.tool
```

---

## Meta-Anomaly Detection

The meta-observability system trains an Isolation Forest on Prometheus metrics to detect deviations from "time-of-day" baselines.

### How it works

1. Every minute, a feature vector is extracted from current metrics
2. Features include: ingestion rate, queue depth, VPIN, p99 latency, WS connections, time-of-day (cyclical)
3. The model scores each sample; scores below -0.15 are flagged as anomalies
4. Model auto-trains every 24h once 48h of data is collected

### Model location

`project_oracle/models/meta_anomaly_v1.pt` (joblib format)

### Check detector state

```python
from services.meta_observability import meta_detector
print(meta_detector.get_state())
```

---

## Incident Post-Mortems

### Create manually

```bash
python3 scripts/start_incident.py \
  --alert-id "AnomalyDetected-2026-05-20" \
  --title "VPIN spike on SPY" \
  --severity CRITICAL \
  --category data
```

### Auto-creation

When a CRITICAL alert is acknowledged via the phone callback URL (`/api/alerts/acknowledge`), a post-mortem skeleton is auto-created at `docs/INCIDENTS/<date>_<slug>.md`.

### Template

See `docs/INCIDENTS/_template.md` for the full template with sections: Title, Severity, Services Affected, Detection, Timeline, Root Cause, Remediation, Action Items, Lessons Learned.

---

## Troubleshooting

### Grafana shows "No data"

1. Check Prometheus is scraping: http://localhost:9090/targets
2. Check the app is running: `curl http://localhost:8000/metrics`
3. Verify datasource in Grafana: Configuration → Data Sources → Prometheus → Test

### Alerts not firing

1. Check Prometheus rules: http://localhost:9090/rules
2. Check Alertmanager: http://localhost:9093/#/alerts
3. Verify webhook is reachable: `curl -X POST http://localhost:8000/api/alerts/fire -H 'Content-Type: application/json' -d '{"alert_id":"test","severity":"CRITICAL","title":"test","message":"test"}'`

### Phone alerts not working

1. Check Twilio credentials in `.env`
2. Check dispatcher status: `curl http://localhost:8000/api/alerts/status`
3. Review logs: `tail -f backend/logs/app.log | grep -i alert`

### High memory usage

- Prometheus retention is 30d. Reduce with `--storage.tsdb.retention.time=7d`
- DuckDB is in-memory. Monitor `floww_duckdb_queue_depth` for backpressure
