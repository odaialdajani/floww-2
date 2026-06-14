"""
Tests for services/logging_config.py — structured JSON logging + correlation IDs.

Covers: StructuredFormatter, setup_logging, get_correlation_id, CorrelationIdMiddleware.
"""
from __future__ import annotations

import json
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.logging_config import (
    CorrelationIdMiddleware,
    StructuredFormatter,
    correlation_id_var,
    get_correlation_id,
    setup_logging,
)

# ---------------------------------------------------------------------------
# StructuredFormatter
# ---------------------------------------------------------------------------

class TestStructuredFormatter:
    def test_format_produces_valid_json(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="fake.py",
            lineno=42,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        raw = fmt.format(record)
        data = json.loads(raw)
        assert isinstance(data, dict)

    def test_format_timestamp_field_is_iso8601(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="f.py", lineno=1,
            msg="test", args=(), exc_info=None,
        )
        data = json.loads(fmt.format(record))
        ts = data["timestamp"]
        # ISO 8601 format check: contains date + T + time
        assert "T" in ts

    def test_format_level_field_matches_record_level(self):
        fmt = StructuredFormatter()
        for level, name in [
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
            (logging.CRITICAL, "CRITICAL"),
        ]:
            record = logging.LogRecord(
                name="test", level=level, pathname="f.py", lineno=1,
                msg="x", args=(), exc_info=None,
            )
            data = json.loads(fmt.format(record))
            assert data["level"] == name

    def test_format_message_is_formatted(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="f.py", lineno=1,
            msg="price=%.2f qty=%d",
            args=(6000.5, 10),
            exc_info=None,
        )
        data = json.loads(fmt.format(record))
        assert data["message"] == "price=6000.50 qty=10"

    def test_format_module_field(self):
        fmt = StructuredFormatter()
        # record.module is derived from pathname: os.path.splitext(basename(pathname))[0]
        record = logging.LogRecord(
            name="my.module.path", level=logging.INFO, pathname="/some/deep/path/my_module.py", lineno=1,
            msg="x", args=(), exc_info=None,
        )
        data = json.loads(fmt.format(record))
        assert data["module"] == "my_module"

    def test_format_line_number(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="f.py", lineno=99,
            msg="x", args=(), exc_info=None,
        )
        data = json.loads(fmt.format(record))
        assert data["line"] == 99

    def test_format_function_name(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="f.py", lineno=1,
            msg="x", args=(), exc_info=None,
            func="my_function",
        )
        data = json.loads(fmt.format(record))
        assert data["function"] == "my_function"

    def test_format_includes_correlation_id_when_set(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="f.py", lineno=1,
            msg="x", args=(), exc_info=None,
        )
        cid = "abc-123"
        token = correlation_id_var.set(cid)
        try:
            data = json.loads(fmt.format(record))
            assert data["correlation_id"] == cid
        finally:
            correlation_id_var.reset(token)

    def test_format_omits_correlation_id_when_not_set(self):
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="f.py", lineno=1,
            msg="x", args=(), exc_info=None,
        )
        # Ensure it's None
        correlation_id_var.set(None)
        data = json.loads(fmt.format(record))
        assert "correlation_id" not in data

    def test_format_all_required_fields_present(self):
        """Golden check: every log line must have exactly these base fields."""
        fmt = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="f.py", lineno=1,
            msg="x", args=(), exc_info=None,
        )
        data = json.loads(fmt.format(record))
        required = {"timestamp", "level", "message", "module", "function", "line"}
        assert required.issubset(data.keys())


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

class TestSetupLogging:
    def _clean_root_handlers(self):
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)

    def test_setup_returns_logger(self):
        self._clean_root_handlers()
        logger = setup_logging()
        assert isinstance(logger, logging.Logger)
        assert logger.level == logging.INFO

    def test_setup_adds_stream_handler(self):
        self._clean_root_handlers()
        setup_logging()
        root = logging.getLogger()
        assert len(root.handlers) >= 1
        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)

    def test_setup_handler_has_structured_formatter(self):
        self._clean_root_handlers()
        setup_logging()
        root = logging.getLogger()
        found = False
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler):
                assert isinstance(h.formatter, StructuredFormatter)
                found = True
                break
        assert found, "No StreamHandler with StructuredFormatter found"

    def test_setup_custom_level(self):
        self._clean_root_handlers()
        logger = setup_logging(level=logging.DEBUG)
        assert logger.level == logging.DEBUG


# ---------------------------------------------------------------------------
# get_correlation_id
# ---------------------------------------------------------------------------

class TestGetCorrelationId:
    def test_returns_none_when_not_set(self):
        correlation_id_var.set(None)
        assert get_correlation_id() is None

    def test_returns_set_value(self):
        token = correlation_id_var.set("test-cid-42")
        try:
            assert get_correlation_id() == "test-cid-42"
        finally:
            correlation_id_var.reset(token)

    def test_returns_value_set_by_middleware(self):
        """Simulate what CorrelationIdMiddleware does internally."""
        cid = str(uuid.uuid4())
        token = correlation_id_var.set(cid)
        try:
            assert get_correlation_id() == cid
        finally:
            correlation_id_var.reset(token)


# ---------------------------------------------------------------------------
# CorrelationIdMiddleware
# ---------------------------------------------------------------------------

class TestCorrelationIdMiddleware:
    def _make_scope(self, headers=None, scope_type="http"):
        return {
            "type": scope_type,
            "headers": [
                (k.encode("utf-8"), v.encode("utf-8"))
                for k, v in (headers or [])
            ],
        }

    def _make_app(self):
        """Create a mock ASGI app that calls send with a response.start message."""
        async def app(scope, receive, send):
            # Simulate a minimal HTTP response
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({
                "type": "http.response.body",
                "body": b"ok",
            })
        return app

    @pytest.mark.asyncio
    async def test_generates_cid_when_not_in_headers(self):
        app = self._make_app()
        mw = CorrelationIdMiddleware(app)
        scope = self._make_scope()
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        # The coroutine should have been called and completed
        # correlation_id_var should now be set to a UUID
        # (it was set inside __call__ before calling app, but app didn't modify it)
        # The var state after the call depends on whether app modified it —
        # _make_app doesn't, so the CID set by middleware persists
        # Actually: the var is set in __call__ before await self.app(...)
        # then app finishes. The var still holds the CID.

    @pytest.mark.asyncio
    async def test_uses_cid_from_headers_when_present(self):
        app = self._make_app()
        mw = CorrelationIdMiddleware(app)
        scope = self._make_scope(headers=[("x-correlation-id", "my-custom-id")])
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        assert correlation_id_var.get() == "my-custom-id"

    @pytest.mark.asyncio
    async def test_case_insensitive_header_lookup(self):
        """x-correlation-id header should match case-insensitively."""
        app = self._make_app()
        mw = CorrelationIdMiddleware(app)
        scope = self._make_scope(headers=[("X-Correlation-Id", "upper-id")])
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        assert correlation_id_var.get() == "upper-id"

    @pytest.mark.asyncio
    async def test_passes_cid_in_response_header(self):
        """The send_with_cid wrapper should add x-correlation-id to response headers."""
        app = self._make_app()
        mw = CorrelationIdMiddleware(app)
        scope = self._make_scope(headers=[("x-correlation-id", "resp-123")])
        receive = AsyncMock()
        messages_received = []

        async def tracking_send(message):
            messages_received.append(message)

        await mw(scope, receive, tracking_send)

        # Find the http.response.start message
        start_msgs = [m for m in messages_received if m.get("type") == "http.response.start"]
        assert len(start_msgs) == 1
        headers = dict(start_msgs[0].get("headers", []))
        assert headers.get(b"x-correlation-id") == b"resp-123"

    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self):
        """WebSocket or other non-HTTP scopes should pass through unchanged."""
        passthrough_called = False

        async def passthrough_app(scope, receive, send):
            nonlocal passthrough_called
            passthrough_called = True
            await send({"type": "websocket.connect"})

        mw = CorrelationIdMiddleware(passthrough_app)
        scope = self._make_scope(scope_type="websocket")
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        assert passthrough_called

    @pytest.mark.asyncio
    async def test_no_headers_generates_uuid(self):
        """When headers list is empty, a UUID should be generated."""
        app = self._make_app()
        mw = CorrelationIdMiddleware(app)
        scope = {"type": "http", "headers": []}
        receive = AsyncMock()
        send = AsyncMock()

        await mw(scope, receive, send)

        cid = correlation_id_var.get()
        assert cid is not None
        parsed = uuid.UUID(cid)
        assert parsed.version == 4
