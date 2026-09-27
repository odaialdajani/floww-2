"""
backend/services/runbook_executor.py

Automated Runbook Execution — for common alerts, executes predefined
diagnostic and remediation steps automatically.

Architecture:
  - Runbooks are defined as Python callables (or loaded from markdown).
  - Each runbook has: trigger condition, steps, verification, rollback.
  - Executor runs steps sequentially, logs each action, and reports results.
  - Human override is always available via kill switch.

Supported runbooks:
  - high_latency: Check resources → restart service if needed → verify
  - ingestion_stall: Check token → check WS → restart streamer
  - queue_backpressure: Check queue → flush → scale if needed
  - vpin_anomaly: Explain → adjust thresholds → notify

Safety:
  - Each step has a timeout (default 30s).
  - Circuit breaker stops after 3 consecutive failures.
  - All actions are logged to the audit trail.
  - kill_switch file (/tmp/runbook_kill_switch) can halt all execution.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)
log = logging.getLogger(__name__)

KILL_SWITCH_PATH = "/tmp/runbook_kill_switch"

# Maximum consecutive auto-remediation failures before circuit break
MAX_FAILURES = 3

# Default step timeout (seconds)
STEP_TIMEOUT = 30


@dataclass
class RunbookStep:
    """A single step in a runbook."""
    name: str
    action: str  # Description of what this step does
    command: str | None = None  # Shell command to execute (optional)
    check_fn: str | None = None  # Name of a check function (optional)
    timeout: int = STEP_TIMEOUT
    critical: bool = False  # If True, failure stops the runbook


@dataclass
class RunbookResult:
    """Result of executing a runbook."""
    runbook_name: str
    alert_id: str
    success: bool
    steps_executed: list[dict[str, Any]]
    start_time: str
    end_time: str
    duration_seconds: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runbook_name": self.runbook_name,
            "alert_id": self.alert_id,
            "success": self.success,
            "steps_executed": self.steps_executed,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


@dataclass
class RunbookRegistry:
    """Registry of all available runbooks."""

    def __init__(self):
        self._runbooks: dict[str, list[RunbookStep]] = {}
        self._failure_counts: dict[str, int] = {}
        self._register_defaults()

    def register(self, name: str, steps: list[RunbookStep]):
        """Register a runbook."""
        self._runbooks[name] = steps
        self._failure_counts[name] = 0

    def get(self, name: str) -> list[RunbookStep] | None:
        """Get a runbook by name."""
        return self._runbooks.get(name)

    def list_runbooks(self) -> list[str]:
        """List all registered runbook names."""
        return list(self._runbooks.keys())

    def _register_defaults(self):
        """Register built-in runbooks."""

        # ── High Latency Runbook ──────────────────────────────────────
        self.register("high_latency", [
            RunbookStep(
                name="check_resources",
                action="Check CPU, memory, and disk usage",
                command="top -l 1 -n 5 | head -20 && df -h / | tail -1",
                timeout=15,
            ),
            RunbookStep(
                name="check_duckdb",
                action="Check DuckDB queue depth",
                command="curl -s http://localhost:8000/api/metrics | grep duckdb_queue_depth || echo 'N/A'",
                timeout=10,
            ),
            RunbookStep(
                name="check_ws_connections",
                action="Check WebSocket connection count",
                command="curl -s http://localhost:8000/api/ws/status | python3 -c \"import sys,json; d=json.load(sys.stdin); logger.info(f'Connections: {d.get(\\\"connections\\\",\\\"N/A\\\")}')\" 2>/dev/null || echo 'Endpoint not available'",
                timeout=10,
            ),
            RunbookStep(
                name="restart_if_needed",
                action="Restart backend service if queue depth > 10000 or WS connections = 0",
                command=(
                    "QUEUE=$(curl -s http://localhost:8000/api/metrics 2>/dev/null | grep 'floww_duckdb_queue_depth ' | awk '{print $2}'); "
                    "if [ -n \"$QUEUE\" ] && [ \"${QUEUE%.*}\" -gt 10000 ] 2>/dev/null; then "
                    "  echo 'Queue depth critical, restarting backend...'; "
                    "  docker compose -f /Users/nav/GitHub/floww/docker-compose.yml restart backend 2>/dev/null || echo 'Manual restart required'; "
                    "else "
                    "  echo 'No restart needed'; "
                    "fi"
                ),
                timeout=30,
                critical=False,
            ),
            RunbookStep(
                name="verify_latency",
                action="Verify latency improved post-remediation",
                command="curl -s -o /dev/null -w '%{time_total}' http://localhost:8000/api/health 2>/dev/null || echo 'N/A'",
                timeout=10,
            ),
        ])

        # ── Ingestion Stall Runbook ───────────────────────────────────
        # Schwab steps removed 2026-09-27. They called
        # /api/auth/schwab/status and "restart the Schwab streamer" — routes
        # and a module that no longer exist, so the runbook could only ever
        # print the fallback string. The real ingestion path is Public.com.
        self.register("ingestion_stall", [
            RunbookStep(
                name="check_data_budget",
                action="Check Public.com token budget and lane health",
                command="curl -s http://localhost:8000/api/public/budget 2>/dev/null | python3 -m json.tool 2>/dev/null || echo 'budget endpoint not available'",
                timeout=10,
            ),
            RunbookStep(
                name="check_databento",
                action="Check Databento API reachability (open-interest overlay)",
                command="curl -s -o /dev/null -w '%{http_code}' --max-time 5 'https://hist.databento.com/v0/mds/mbp/SPY' 2>/dev/null || echo 'unreachable'",
                timeout=15,
            ),
            RunbookStep(
                name="check_upstream_health",
                action="Check backend data-provider health",
                command="curl -s http://localhost:8000/api/data/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo 'health endpoint not available'",
                timeout=10,
            ),
            RunbookStep(
                name="restart_backend",
                action="Restart the backend if the feed is wedged",
                command=(
                    "if ! curl -sf --max-time 5 http://localhost:8000/health >/dev/null 2>&1; then "
                    "  echo 'backend unhealthy, restarting...'; "
                    "  docker compose restart backend 2>/dev/null || echo 'Manual restart required'; "
                    "else "
                    "  echo 'backend healthy'; "
                    "fi"
                ),
                timeout=20,
                critical=False,
            ),
        ])

        # ── Queue Backpressure Runbook ────────────────────────────────
        self.register("queue_backpressure", [
            RunbookStep(
                name="check_queue_depth",
                action="Get current DuckDB queue depth",
                command="curl -s http://localhost:8000/api/metrics 2>/dev/null | grep 'floww_duckdb_queue_depth ' || echo 'N/A'",
                timeout=10,
            ),
            RunbookStep(
                name="check_lock_contention",
                action="Check for long-running DuckDB queries",
                command="ps aux | grep -i duckdb | grep -v grep | head -5 || echo 'No DuckDB processes visible'",
                timeout=10,
            ),
            RunbookStep(
                name="force_flush",
                action="Force queue flush if depth > 5000",
                command=(
                    "QUEUE=$(curl -s http://localhost:8000/api/metrics 2>/dev/null | grep 'floww_duckdb_queue_depth ' | awk '{print $2}'); "
                    "if [ -n \"$QUEUE\" ] && [ \"${QUEUE%.*}\" -gt 5000 ] 2>/dev/null; then "
                    "  echo 'Triggering queue flush...'; "
                    "  curl -s -X POST http://localhost:8000/api/admin/queue/flush 2>/dev/null || echo 'Flush endpoint not available'; "
                    "else "
                    "  echo 'Queue depth acceptable'; "
                    "fi"
                ),
                timeout=15,
            ),
        ])


class RunbookExecutor:
    """Executes runbooks in response to alerts.

    Safety features:
    - Kill switch: Create /tmp/runbook_kill_switch to halt all execution.
    - Circuit breaker: After MAX_FAILURES consecutive failures for a
      runbook type, auto-remediation is disabled until manually reset.
    - Audit logging: Every step result is logged.
    """

    def __init__(self, registry: RunbookRegistry | None = None):
        self._registry = registry or RunbookRegistry()
        self._execution_log: list[RunbookResult] = []

    @property
    def registry(self) -> RunbookRegistry:
        return self._registry

    def _check_kill_switch(self) -> bool:
        """Check if the kill switch file exists."""
        return os.path.exists(KILL_SWITCH_PATH)

    async def execute(
        self,
        runbook_name: str,
        alert_id: str,
        dry_run: bool = False,
    ) -> RunbookResult:
        """Execute a runbook.

        Args:
            runbook_name: Name of the registered runbook.
            alert_id: The alert that triggered this runbook.
            dry_run: If True, log steps but don't execute commands.

        Returns:
            RunbookResult with execution details.
        """
        start_ts = datetime.now(UTC).isoformat()
        start_time = time.time()
        steps_executed = []

        # Check kill switch
        if self._check_kill_switch():
            log.warning(f"[RUNBOOK] Kill switch active — skipping {runbook_name}")
            return RunbookResult(
                runbook_name=runbook_name,
                alert_id=alert_id,
                success=False,
                steps_executed=steps_executed,
                start_time=start_ts,
                end_time=datetime.now(UTC).isoformat(),
                duration_seconds=0.0,
                error="Kill switch active",
            )

        # Check circuit breaker
        if self._registry._failure_counts.get(runbook_name, 0) >= MAX_FAILURES:
            log.warning(f"[RUNBOOK] Circuit breaker open for {runbook_name} — skipping")
            return RunbookResult(
                runbook_name=runbook_name,
                alert_id=alert_id,
                success=False,
                steps_executed=steps_executed,
                start_time=start_ts,
                end_time=datetime.now(UTC).isoformat(),
                duration_seconds=0.0,
                error=f"Circuit breaker open ({MAX_FAILURES} consecutive failures)",
            )

        # Get runbook steps
        steps = self._registry.get(runbook_name)
        if not steps:
            return RunbookResult(
                runbook_name=runbook_name,
                alert_id=alert_id,
                success=False,
                steps_executed=steps_executed,
                start_time=start_ts,
                end_time=datetime.now(UTC).isoformat(),
                duration_seconds=0.0,
                error=f"Runbook '{runbook_name}' not found",
            )

        # Execute steps
        success = True
        error_msg = None

        for step in steps:
            step_result = {
                "name": step.name,
                "action": step.action,
                "success": True,
                "output": "",
                "duration_seconds": 0.0,
            }

            if dry_run:
                log.info(f"[RUNBOOK DRY-RUN] {runbook_name}/{step.name}: {step.action}")
                step_result["output"] = f"[DRY-RUN] {step.action}"
            elif step.command:
                try:
                    proc = await asyncio.create_subprocess_shell(
                        step.command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(), timeout=step.timeout
                        )
                        output = stdout.decode().strip() or stderr.decode().strip() or "(no output)"
                        step_result["output"] = output[:500]  # Truncate long output
                        step_result["success"] = proc.returncode == 0
                    except TimeoutError:
                        proc.kill()
                        await proc.wait()
                        step_result["success"] = False
                        step_result["output"] = f"Timeout after {step.timeout}s"
                        log.warning(f"[RUNBOOK TIMEOUT] {runbook_name}/{step.name}")
                except Exception as e:
                    step_result["success"] = False
                    step_result["output"] = str(e)[:200]
                    log.error(f"[RUNBOOK ERROR] {runbook_name}/{step.name}: {e}")
            else:
                step_result["output"] = "(no command — informational step)"

            step_result["duration_seconds"] = round(time.time() - start_time, 2)
            steps_executed.append(step_result)

            if not step_result["success"] and step.critical:
                success = False
                error_msg = f"Critical step '{step.name}' failed: {step_result['output'][:100]}"
                log.error(f"[RUNBOOK FAIL] {runbook_name}/{step.name}: {error_msg}")
                break
            elif not step_result["success"]:
                log.warning(f"[RUNBOOK STEP FAIL] {runbook_name}/{step.name}: non-critical")

        # Circuit breaker tracking
        if not success:
            self._registry._failure_counts[runbook_name] = \
                self._registry._failure_counts.get(runbook_name, 0) + 1
        else:
            self._registry._failure_counts[runbook_name] = 0

        duration = round(time.time() - start_time, 2)
        result = RunbookResult(
            runbook_name=runbook_name,
            alert_id=alert_id,
            success=success,
            steps_executed=steps_executed,
            start_time=start_ts,
            end_time=datetime.now(UTC).isoformat(),
            duration_seconds=duration,
            error=error_msg,
        )

        self._execution_log.append(result)
        log.info(
            f"[RUNBOOK DONE] {runbook_name}: success={success}, "
            f"steps={len(steps_executed)}, duration={duration}s"
        )
        return result

    def get_execution_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent execution history."""
        return [r.to_dict() for r in self._execution_log[-limit:]]

    def reset_circuit_breaker(self, runbook_name: str):
        """Reset the circuit breaker for a runbook."""
        self._registry._failure_counts[runbook_name] = 0
        log.info(f"[RUNBOOK] Circuit breaker reset for {runbook_name}")


# Global singleton
executor = RunbookExecutor()
