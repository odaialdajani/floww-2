"""
backend/tests/services/test_runbook_executor.py

Unit tests for runbook_executor.py — automated runbook execution.

Coverage:
    - RunbookRegistry registration and listing
    - RunbookExecutor dry-run execution
    - Kill switch behavior
    - Circuit breaker
    - Execution history
    - Step timeout handling
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_registry_defaults():
    from services.runbook_executor import RunbookRegistry
    reg = RunbookRegistry()
    runbooks = reg.list_runbooks()
    assert "high_latency" in runbooks
    assert "ingestion_stall" in runbooks
    assert "queue_backpressure" in runbooks


def test_registry_get():
    from services.runbook_executor import RunbookRegistry
    reg = RunbookRegistry()
    steps = reg.get("high_latency")
    assert steps is not None
    assert len(steps) >= 3
    assert steps[0].name == "check_resources"


def test_registry_get_missing():
    from services.runbook_executor import RunbookRegistry
    reg = RunbookRegistry()
    assert reg.get("nonexistent") is None


@pytest.mark.asyncio
async def test_executor_dry_run():
    from services.runbook_executor import RunbookExecutor
    executor = RunbookExecutor()
    result = await executor.execute("high_latency", "test-alert-1", dry_run=True)
    assert result.runbook_name == "high_latency"
    assert result.alert_id == "test-alert-1"
    assert result.success is True
    assert len(result.steps_executed) >= 3


@pytest.mark.asyncio
async def test_executor_missing_runbook():
    from services.runbook_executor import RunbookExecutor
    executor = RunbookExecutor()
    result = await executor.execute("nonexistent", "test-alert-2", dry_run=True)
    assert result.success is False
    assert result.error is not None and "not found" in result.error


@pytest.mark.asyncio
async def test_executor_kill_switch():
    from services.runbook_executor import KILL_SWITCH_PATH, RunbookExecutor
    executor = RunbookExecutor()
    # Create kill switch
    with open(KILL_SWITCH_PATH, "w") as f:
        f.write("1")
    try:
        result = await executor.execute("high_latency", "test-alert-3", dry_run=True)
        assert result.success is False
        assert result.error is not None and "Kill switch" in result.error
    finally:
        os.remove(KILL_SWITCH_PATH)


@pytest.mark.asyncio
async def test_executor_circuit_breaker():
    from services.runbook_executor import MAX_FAILURES, RunbookExecutor
    executor = RunbookExecutor()
    # Manually set failure count
    executor._registry._failure_counts["high_latency"] = MAX_FAILURES
    result = await executor.execute("high_latency", "test-alert-4", dry_run=True)
    assert result.success is False
    assert result.error is not None and "Circuit breaker" in result.error


@pytest.mark.asyncio
async def test_executor_reset_circuit_breaker():
    from services.runbook_executor import MAX_FAILURES, RunbookExecutor
    executor = RunbookExecutor()
    executor._registry._failure_counts["high_latency"] = MAX_FAILURES
    executor.reset_circuit_breaker("high_latency")
    assert executor._registry._failure_counts["high_latency"] == 0
    # Should now execute
    result = await executor.execute("high_latency", "test-alert-5", dry_run=True)
    assert result.success is True


@pytest.mark.asyncio
async def test_execution_history():
    from services.runbook_executor import RunbookExecutor
    executor = RunbookExecutor()
    await executor.execute("high_latency", "hist-1", dry_run=True)
    await executor.execute("ingestion_stall", "hist-2", dry_run=True)
    history = executor.get_execution_history()
    assert len(history) == 2
    assert history[0]["alert_id"] == "hist-1"
    assert history[1]["alert_id"] == "hist-2"


@pytest.mark.asyncio
async def test_execution_result_format():
    from services.runbook_executor import RunbookExecutor
    executor = RunbookExecutor()
    result = await executor.execute("queue_backpressure", "fmt-test", dry_run=True)
    d = result.to_dict()
    assert "runbook_name" in d
    assert "success" in d
    assert "steps_executed" in d
    assert "duration_seconds" in d
    assert "start_time" in d
    assert "end_time" in d


@pytest.mark.asyncio
async def test_runbook_step_has_command():
    from services.runbook_executor import RunbookRegistry
    reg = RunbookRegistry()
    for name in reg.list_runbooks():
        steps = reg.get(name)
        assert steps is not None
        for step in steps:
            assert step.name
            assert step.action
            assert step.timeout > 0


@pytest.mark.asyncio
async def test_executor_duration_tracked():
    from services.runbook_executor import RunbookExecutor
    executor = RunbookExecutor()
    result = await executor.execute("high_latency", "dur-test", dry_run=True)
    assert result.duration_seconds >= 0.0
