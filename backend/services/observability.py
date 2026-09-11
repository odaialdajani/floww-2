"""
backend/services/observability.py

Prometheus metrics exposition for Project Oracle.
Central registry of all floww_ metrics. Import and call from any service.

Usage:
    from services.observability import metrics

    # In VPIN engine:
    metrics.vpin_current.labels(ticker="SPY").set(0.72)

    # In FastAPI middleware:
    metrics.api_request_duration_seconds.labels(
        route="/api/vpin/{ticker}", method="GET", status="200"
    ).observe(0.023)

    # In WebSocket connect/disconnect:
    metrics.websocket_connections.labels(topic="ticks").inc()
    metrics.websocket_connections.labels(topic="ticks").dec()
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---------------------------------------------------------------------------
# Registry — isolated so tests don't pollute global
# ---------------------------------------------------------------------------
REGISTRY = CollectorRegistry()

# ---------------------------------------------------------------------------
# Ingestion metrics
# ---------------------------------------------------------------------------
ingestion_messages_total = Counter(
    "floww_ingestion_messages_total",
    "Total market data messages ingested",
    labelnames=["symbol", "kind"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# DuckDB metrics
# ---------------------------------------------------------------------------
duckdb_queue_depth = Gauge(
    "floww_duckdb_queue_depth",
    "Current number of items in the DuckDB write queue",
    registry=REGISTRY,
)

duckdb_batch_size = Histogram(
    "floww_duckdb_batch_size",
    "Number of rows per DuckDB batch flush",
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# VPIN / Toxicity metrics
# ---------------------------------------------------------------------------
vpin_current = Gauge(
    "floww_vpin_current",
    "Current VPIN value (0-1) per ticker",
    labelnames=["ticker"],
    registry=REGISTRY,
)

qi_zscore_current = Gauge(
    "floww_qi_zscore_current",
    "Current Quote Imbalance z-score per ticker",
    labelnames=["ticker"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Trinity Alignment
# ---------------------------------------------------------------------------
trinity_score = Gauge(
    "floww_trinity_score",
    "Trinity Alignment Index score (0-100)",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Anomaly Detection
# ---------------------------------------------------------------------------
anomaly_score = Gauge(
    "floww_anomaly_score",
    "Current anomaly reconstruction error per ticker",
    labelnames=["ticker"],
    registry=REGISTRY,
)

anomaly_detected_total = Counter(
    "floww_anomaly_detected_total",
    "Total number of anomaly threshold breaches",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# API / HTTP metrics
# ---------------------------------------------------------------------------
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
    registry=REGISTRY,
)

api_request_duration_seconds = Histogram(
    "floww_api_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["route", "method", "status"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# WebSocket metrics
# ---------------------------------------------------------------------------
websocket_connections = Gauge(
    "floww_websocket_connections",
    "Current number of active WebSocket connections per topic",
    labelnames=["topic"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Helper: generate Prometheus exposition format
# ---------------------------------------------------------------------------
def get_metrics_bytes() -> bytes:
    """Return all metrics in Prometheus text exposition format."""
    return generate_latest(REGISTRY)


def get_metrics_content_type() -> str:
    """Return the content type for Prometheus metrics."""
    return CONTENT_TYPE_LATEST


# ---------------------------------------------------------------------------
# Metrics namespace — duckdb_engine does `from services.observability import metrics`
# ---------------------------------------------------------------------------
class _MetricsNamespace:
    """Simple namespace that exposes all metric objects as attributes."""
    def __init__(self):
        # Copy all module-level metric objects into this namespace
        import sys
        mod = sys.modules[__name__]
        for name in dir(mod):
            obj = getattr(mod, name)
            if not name.startswith("_") and not callable(obj) and not isinstance(obj, type):
                setattr(self, name, obj)

# ---------------------------------------------------------------------------
# Cost / Budget metrics
# ---------------------------------------------------------------------------
cost_usd_daily = Gauge(
    "floww_cost_usd_daily",
    "Daily spend in USD per provider",
    labelnames=["provider"],
    registry=REGISTRY,
)

cost_budget_pct = Gauge(
    "floww_cost_budget_pct",
    "Budget utilization percentage per provider (0-100)",
    labelnames=["provider"],
    registry=REGISTRY,
)

cost_budget_usd = Gauge(
    "floww_cost_budget_usd",
    "Total budget in USD per provider",
    labelnames=["provider"],
    registry=REGISTRY,
)

llm_tokens_total = Counter(
    "floww_llm_tokens_total",
    "Total LLM tokens consumed per provider and model",
    labelnames=["provider", "model"],
    registry=REGISTRY,
)

hf_bytes_downloaded_total = Counter(
    "floww_hf_bytes_downloaded_total",
    "Total bytes downloaded from HuggingFace",
    registry=REGISTRY,
)

schwab_api_calls_total = Counter(
    "floww_schwab_api_calls_total",
    "Total Schwab API calls made today",
    registry=REGISTRY,
)


# ---------------------------------------------------------------------------
# Data Provider Health metrics
# ---------------------------------------------------------------------------
provider_calls_total = Counter(
    "floww_provider_calls_total",
    "Total data provider API calls",
    labelnames=["provider", "status"],  # status: "success" | "failure" | "rate_limited"
    registry=REGISTRY,
)

provider_success_rate = Gauge(
    "floww_provider_success_rate",
    "Rolling 5-minute success rate per provider (0.0-1.0)",
    labelnames=["provider"],
    registry=REGISTRY,
)

provider_last_success_seconds_ago = Gauge(
    "floww_provider_last_success_seconds_ago",
    "Seconds since last successful call per provider",
    labelnames=["provider"],
    registry=REGISTRY,
)

provider_alerts_fired_total = Counter(
    "floww_provider_alerts_fired_total",
    "Total alerts fired for data provider health issues",
    labelnames=["provider", "alert_type"],  # alert_type: "low_success_rate" | "provider_down" | "repeated_failures"
    registry=REGISTRY,
)

quarantine_total = Counter(
    "floww_quarantine_total",
    "Total malformed provider payloads quarantined at the boundary (never raised)",
    labelnames=["source", "reason"],  # reason: short snake_case code from contract_validators
    registry=REGISTRY,
)

sweep_last_unixtime = Gauge(
    "floww_sweep_last_unixtime",
    "Wall-clock unixtime of the last completed universe sweep (dead-man gauge; 0 = never)",
    registry=REGISTRY,
)

yfinance_calls_total = Counter(
    "floww_yfinance_calls_total",
    "Total yfinance calls (spot, chains, history)",
    labelnames=["endpoint", "status"],
    registry=REGISTRY,
)

yfinance_success_rate = Gauge(
    "floww_yfinance_success_rate",
    "Rolling yfinance success rate (0.0-1.0)",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Fill Quality / Slippage metrics
# ---------------------------------------------------------------------------
fill_slippage_bps = Histogram(
    "floww_fill_slippage_bps",
    "Fill slippage in basis points (positive = adverse)",
    labelnames=["ticker", "side"],
    buckets=[0, 0.5, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000],
    registry=REGISTRY,
)

fills_total = Counter(
    "floww_fills_total",
    "Total fills recorded",
    labelnames=["ticker", "side"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Circuit Breaker metrics
# ---------------------------------------------------------------------------
circuit_breaker_state = Gauge(
    "floww_circuit_breaker_state",
    "Circuit breaker state per provider (0=closed, 1=open, 2=half_open)",
    labelnames=["provider"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Cache & Rate Limit metrics
# ---------------------------------------------------------------------------
cache_hit_ratio = Gauge(
    "floww_cache_hit_ratio",
    "Cache hit ratio (0.0-1.0) for DuckDB fallback serving",
    registry=REGISTRY,
)

rate_limit_429_count = Counter(
    "floww_rate_limit_429_total",
    "Total HTTP 429 responses served (rate limit exceeded)",
    labelnames=["client_ip"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Exception handler redaction metrics (P2.5-D)
# ---------------------------------------------------------------------------
# Defined here (alongside all other floww_ Prom metrics), then re-exported
# in error_tracking.py so server.py:global_exception_handler can call
# `error_tracking.redacted_500_count.labels(env=_env).inc()` directly
# without an extra import surface — keeps prometheus_client and the
# registry confined to services/observability.py.
redacted_500_count = Counter(
    "floww_redacted_500_total",
    "Total 500 responses served with a redacted payload (env branch fired).",
    labelnames=["env"],
    registry=REGISTRY,
)


metrics = _MetricsNamespace()
