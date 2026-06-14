"""
Tests for services/graph_updater.py — GraphUpdater stub / placeholder.

The current implementation is a stub (module-level logger only, no public
class or functions yet). These tests pin the module's current public surface
so that when the implementation is fleshed out, the tests will fail and
signal that they need updating.
"""
from __future__ import annotations

import logging

import pytest

from services import graph_updater


class TestGraphUpdaterModule:
    def test_module_imports(self):
        """Module should be importable."""
        assert hasattr(graph_updater, "logger")

    def test_logger_name(self):
        """Logger should be named 'graph_updater' for correct log routing."""
        assert graph_updater.logger.name == "graph_updater"

    def test_logger_is_logger_instance(self):
        assert isinstance(graph_updater.logger, logging.Logger)

    def test_module_has_docstring(self):
        assert graph_updater.__doc__ is not None
        assert "graph" in graph_updater.__doc__.lower()
