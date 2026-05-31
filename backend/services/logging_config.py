"""
backend/services/logging_config.py
Structured JSON logging with correlation IDs for request tracing.
"""
import contextvars
import json
import logging
import uuid
from datetime import datetime, timezone

correlation_id_var = contextvars.ContextVar('correlation_id', default=None)


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        cid = correlation_id_var.get()
        if cid:
            log_data["correlation_id"] = cid
        return json.dumps(log_data)


def setup_logging(level=logging.INFO):
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(handler)
    return logger


def get_correlation_id():
    return correlation_id_var.get()


class CorrelationIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cid = None
        for key, value in scope.get("headers", []):
            if key.lower() == b"x-correlation-id":
                cid = value.decode("utf-8")
                break
        if not cid:
            cid = str(uuid.uuid4())
        correlation_id_var.set(cid)

        async def send_with_cid(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", cid.encode("utf-8")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cid)
