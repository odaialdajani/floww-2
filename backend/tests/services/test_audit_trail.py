"""
tests/services/test_audit_trail.py

Unit tests for services/audit_trail.py — the audit trail service.

This module is currently a stub (SEC Rule 17a-4 inspired immutable hash-chained
audit trail for write actions). These tests cover the existing surface:
    - logger is correctly named
    - module imports cleanly
    - module-level docstring covers expected API contract

As the module is expanded with record/verify functions, tests here pin the
expected API contract from the module docstring:
    Fields: timestamp, actor, action_type, target, before_state, after_state,
            ip, user_agent, request_id
    Retention: 7 years
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestAuditTrailModule:
    """Test the audit_trail module's basic structure."""

    def test_module_imports(self):
        """audit_trail module imports without errors."""
        import services.audit_trail  # noqa: F401

    def test_logger_exists(self):
        """The module exposes a logger named 'audit_trail'."""
        from services import audit_trail
        assert hasattr(audit_trail, "logger")
        assert audit_trail.logger.name == "audit_trail"

    def test_logger_is_logging_logger(self):
        """The logger is a proper logging.Logger instance."""
        import logging
        from services import audit_trail
        assert isinstance(audit_trail.logger, logging.Logger)

    def test_module_has_docstring(self):
        """The module has a docstring describing its purpose."""
        from services import audit_trail
        doc = audit_trail.__doc__
        assert doc is not None
        assert "audit" in doc.lower()

    def test_docstring_mentions_retention(self):
        """The docstring references the 7-year retention requirement."""
        from services import audit_trail
        doc = audit_trail.__doc__
        assert doc is not None
        assert "7" in doc or "retention" in doc.lower()

    def test_docstring_mentions_sec(self):
        """The docstring references SEC Rule 17a-4."""
        from services import audit_trail
        doc = audit_trail.__doc__
        assert doc is not None
        assert "17a-4" in doc or "SEC" in doc
