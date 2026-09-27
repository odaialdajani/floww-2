"""Compose stacks must be internally consistent and actually runnable.

Three defects lived here, all of which let a stack start in a broken state
rather than fail loudly:

  * `docker-compose.observability.yml` mounted `../prometheus/...` and
    `../grafana/...`. The compose file sits at the repo root, so `../` is the
    repo's PARENT, where neither directory exists. Docker silently creates
    the missing source directories empty, so Prometheus and Grafana came up
    with no config and no dashboards, and reported healthy.
  * Grafana published host port 3000, which `docker-compose.yml` already uses
    for the dev frontend. RUNBOOK.md tells you to bring the observability
    stack up alongside the app, so the second `up` could not bind.
  * `docker-compose.prod.yml` ran Prometheus with no `extra_hosts`, while the
    config it mounts scrapes `host.docker.internal:8000`. On Linux that name
    does not resolve in a container, so the backend was never scraped and
    alerting silently covered nothing.

These are checked statically so CI catches them without a docker daemon.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = [
    "docker-compose.yml",
    "docker-compose.prod.yml",
    "docker-compose.observability.yml",
]


def _load(name: str) -> dict:
    path = REPO_ROOT / name
    assert path.exists(), f"missing compose file: {name}"
    return yaml.safe_load(path.read_text()) or {}


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_compose_file_is_valid_yaml(name):
    assert isinstance(_load(name), dict)


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_no_bind_mount_escapes_the_repo_root(name):
    """`../` in a bind mount points outside the repo, where nothing exists.

    Docker does not error on a missing bind source -- it creates an empty
    directory -- so this class of bug yields a running-but-blind service.
    """
    text = (REPO_ROOT / name).read_text()
    offenders = [
        line.strip()
        for line in text.splitlines()
        if re.search(r":\s*(\.\./)", line) and not line.strip().startswith("#")
    ]
    assert not offenders, f"{name} bind-mounts outside the repo: {offenders}"


@pytest.mark.parametrize("name", COMPOSE_FILES)
def test_every_bind_mount_source_exists(name):
    """A relative bind source must resolve to a real path in the repo."""
    doc = _load(name)
    missing: list[str] = []
    for svc, cfg in (doc.get("services") or {}).items():
        for vol in (cfg or {}).get("volumes") or []:
            if not isinstance(vol, str):
                continue
            src = vol.split(":")[0]
            if not src.startswith((".", "/")):
                continue  # named volume
            if any(ch in src for ch in "{}*$"):
                continue  # templated / glob, not checkable statically
            if not (REPO_ROOT / src).exists():
                missing.append(f"{name}:{svc} -> {src}")
    assert not missing, f"bind-mount sources that do not exist: {missing}"


def test_observability_prometheus_mounts_resolve():
    """The specific regression: six mounts pointed at the repo's parent."""
    for rel in (
        "prometheus/prometheus.yml",
        "prometheus/alerts",
        "prometheus/alertmanager.yml",
        "grafana/provisioning/datasources",
        "grafana/provisioning/dashboards",
        "grafana/dashboards",
    ):
        assert (REPO_ROOT / rel).exists(), f"observability stack needs {rel}"


def _host_ports(name: str) -> set[str]:
    doc = _load(name)
    out: set[str] = set()
    for cfg in (doc.get("services") or {}).values():
        for port in (cfg or {}).get("ports") or []:
            m = re.match(r'"?(\d+):(\d+)"?', str(port))
            if m:
                out.add(m.group(1))
    return out


def test_no_host_port_collides_between_the_two_stacks_run_together():
    """RUNBOOK.md starts observability while the dev stack is up."""
    dev = _host_ports("docker-compose.yml")
    obs = _host_ports("docker-compose.observability.yml")
    clash = dev & obs
    assert not clash, (
        f"host port(s) {sorted(clash)} are published by both the dev stack and "
        "the observability stack; the second `up` cannot bind"
    )


def test_prometheus_scrape_target_is_reachable_from_the_container():
    """host.docker.internal needs extra_hosts on Linux."""
    prom_cfg = (REPO_ROOT / "prometheus" / "prometheus.yml").read_text()
    if "host.docker.internal" not in prom_cfg:
        pytest.skip("prometheus does not scrape host.docker.internal")
    for name in ("docker-compose.prod.yml", "docker-compose.observability.yml"):
        svc = (_load(name).get("services") or {}).get("prometheus")
        assert svc is not None, f"{name} has no prometheus service"
        hosts = svc.get("extra_hosts") or []
        assert any("host.docker.internal" in str(h) for h in hosts), (
            f"{name} prometheus scrapes host.docker.internal but declares no "
            "extra_hosts mapping, so the target cannot resolve on Linux"
        )


def test_grafana_root_url_matches_the_published_host_port():
    """A stale root_url makes Grafana redirect to the wrong origin."""
    doc = _load("docker-compose.observability.yml")
    grafana = doc["services"]["grafana"]
    published = None
    for port in grafana.get("ports") or []:
        m = re.match(r'"?(\d+):(\d+)"?', str(port))
        if m:
            published = m.group(1)
    assert published, "grafana publishes no host port"
    env = " ".join(str(e) for e in grafana.get("environment") or [])
    m = re.search(r"GF_SERVER_ROOT_URL=http://localhost:(\d+)", env)
    if m:
        assert m.group(1) == published, (
            f"GF_SERVER_ROOT_URL says port {m.group(1)} but the host port is "
            f"{published}; Grafana will redirect to the wrong origin"
        )


# ── Alert rules vs. metrics that actually exist ────────────────────────────
#
# An alert whose metric is never emitted can never fire, and Prometheus will
# not complain: the rule loads, the target is simply absent. That is a safety
# net that does not exist while appearing to.
#
# `SchwabTokenExpiring` was exactly that: it watched
# floww_schwab_token_expires_in_seconds, which nothing in the backend emits,
# and told the operator to re-authenticate via /api/schwab/auth -- a route
# that does not exist, for a provider explicitly listed as retired in
# routes/data_providers.py. Removed rather than left as decoration.

ALERT_DIR = REPO_ROOT / "prometheus" / "alerts"


def _alert_metrics() -> set[str]:
    metrics: set[str] = set()
    for path in sorted(ALERT_DIR.glob("*.yml")):
        doc = yaml.safe_load(path.read_text()) or {}
        for group in doc.get("groups") or []:
            for rule in group.get("rules") or []:
                for name in re.findall(r"\b(floww_[a-z_]+)", str(rule.get("expr", ""))):
                    metrics.add(name)
    return metrics


def _backend_declares(metric: str) -> bool:
    """True if any non-test backend module references the metric name."""
    root = REPO_ROOT / "backend"
    for py in root.rglob("*.py"):
        parts = py.parts
        if ".venv" in parts or "tests" in parts:
            continue
        try:
            if metric in py.read_text(errors="ignore"):
                return True
        except OSError:
            continue
    return False


# Prometheus synthesises these from a parent metric rather than the app
# declaring them, so their absence from the source is not a dead alert.
PROMETHEUS_DERIVED_SUFFIXES = ("_count", "_sum", "_bucket")


def test_alert_rules_reference_only_emitted_metrics():
    """An alert on a metric nothing emits can never fire.

    `floww_*_count` / `_sum` / `_bucket` are excluded: Prometheus generates
    those series from the parent histogram/summary, so the backend declaring
    `floww_api_request_duration_seconds` is enough for an alert on
    `floww_api_request_duration_seconds_count`.
    """
    dead = sorted(
        m
        for m in _alert_metrics()
        if not m.endswith(PROMETHEUS_DERIVED_SUFFIXES) and not _backend_declares(m)
    )
    assert not dead, (
        "alert rules watch metrics the backend never emits, so they can never "
        f"fire: {dead}"
    )


def test_no_alert_points_at_a_retired_provider():
    retired = ("schwab", "alphavantage")
    for path in sorted(ALERT_DIR.glob("*.yml")):
        text = path.read_text().lower()
        for name in retired:
            assert name not in text, (
                f"{path.name} references {name}, which "
                "routes/data_providers.py lists as retired"
            )


def test_alert_files_are_valid_yaml():
    files = sorted(ALERT_DIR.glob("*.yml"))
    assert files, "no alert files found"
    for path in files:
        assert isinstance(yaml.safe_load(path.read_text()), dict), path


# ── Schwab is retired. It must not come back as a data source. ─────────────
#
# Schwab was retired as a data feed on 2026-09-03. All market data is
# Public.com (with cvserver / yfinance / Databento fallbacks). What remains is
# dead weight that reads like a live integration:
#
#   * `services/schwab_streamer.py` — zero importers, no key, unreachable
#     host baked in. Its `__init__` even documents that the brokerage account
#     is deleted and a token_manager "MUST be injected (tests pass a mock)".
#   * `services/mock_schwab_feed.py` — synthetic fixture, live-imported by
#     server.py but gated behind FLOWW_ENABLE_MOCK_FEED=1. Legacy name only.
#   * Prometheus rules, ARCHITECTURE.md, and several dispatch docs that
#     described Schwab as a primary data source.
#
# These tests pin the retirement so a future change cannot quietly reintroduce
# a Schwab credential or endpoint on the live path.

SCHWAB = "schwab"
RETIRED_PROVIDERS = (SCHWAB, "alphavantage")


def _non_test_backend_files() -> list[Path]:
    out = []
    for py in sorted((REPO_ROOT / "backend").rglob("*.py")):
        parts = py.parts
        if ".venv" in parts or "tests" in parts or "test" in py.stem:
            continue
        out.append(py)
    return out


def test_no_schwab_endpoint_or_credential_in_live_backend_code():
    """No Schwab URL, env var, or token handling may reach the live path."""
    banned = (
        "schwab.com",           # api/streamer host
        "SCHWAB_API_KEY",
        "SCHWAB_APP_KEY",
        "SCHWAB_SECRET",
        "SCHWAB_ACCESS_TOKEN",
        "SCHWAB_REFRESH_TOKEN",
    )
    offenders: list[str] = []
    for py in _non_test_backend_files():
        if py.name == "schwab_streamer.py":
            continue  # the dead module itself, asserted separately below
        text = py.read_text(errors="ignore")
        for needle in banned:
            if needle in text:
                offenders.append(f"{py.relative_to(REPO_ROOT)}: {needle}")
    assert not offenders, f"Schwab integration points in live code: {offenders}"


def test_schwab_streamer_stays_unreferenced():
    """If something starts importing it, that is a regression to investigate.

    It is not deleted in this branch (it has a reconnect-chaos test suite);
    it is quarantined. The point is that any new importer surfaces here.
    """
    streamer = REPO_ROOT / "backend" / "services" / "schwab_streamer.py"
    if not streamer.exists():
        pytest.skip("schwab_streamer.py has been removed")
    importers = []
    for py in _non_test_backend_files():
        if py == streamer:
            continue
        if "schwab_streamer" in py.read_text(errors="ignore"):
            importers.append(str(py.relative_to(REPO_ROOT)))
    assert not importers, (
        f"{streamer.name} is retired but is now imported by {importers} — if "
        "that is intentional, re-open the retirement decision deliberately"
    )


def test_frontend_has_no_schwab_references():
    """The browser must never talk to, or name, a retired provider."""
    src = REPO_ROOT / "frontend" / "src"
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in src.rglob("*")
        if p.is_file()
        and p.suffix in {".js", ".jsx", ".ts", ".tsx"}
        and SCHWAB in p.read_text(errors="ignore").lower()
    ]
    assert not offenders, f"frontend references Schwab: {offenders}"


def test_retired_providers_are_not_declared_as_live_config():
    """Nothing should read credentials for a retired provider."""
    for name in RETIRED_PROVIDERS:
        for py in _non_test_backend_files():
            if py.name == "schwab_streamer.py":
                continue
            text = py.read_text(errors="ignore")
            assert f"{name.upper()}_API_KEY" not in text, (
                f"{py.relative_to(REPO_ROOT)} reads a {name.upper()}_API_KEY, "
                "but that provider is retired"
            )


def test_docs_do_not_describe_a_retired_provider_as_the_data_source():
    """ARCHITECTURE.md previously showed Schwab feeding the pipeline."""
    arch = (REPO_ROOT / "ARCHITECTURE.md").read_text().lower()
    for line in arch.splitlines():
        if SCHWAB in line and "|" in line:
            assert "dead" in line or "retired" in line, (
                f"ARCHITECTURE.md lists Schwab as an active service: {line.strip()!r}"
            )
    for phrase in ("all market data enters via", "schwab stream  ─", "schwab stream ─"):
        if phrase in arch:
            window = arch[max(0, arch.find(phrase) - 100):arch.find(phrase) + 300]
            assert "dead" in window or "retired" in window, (
                f"ARCHITECTURE.md still describes Schwab as a live data source: {phrase!r}"
            )

