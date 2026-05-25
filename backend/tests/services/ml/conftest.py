"""Conftest for ML tests — gates tests that need model artifacts on disk."""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip tests marked requires_artifacts when model artifacts are not present."""
    models_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "models")
    artifacts_present = os.path.isdir(models_dir) and bool(os.listdir(models_dir))

    if not artifacts_present:
        skip_marker = pytest.mark.skip(reason="model artifacts not present")
        for item in items:
            if item.get_closest_marker("requires_artifacts"):
                item.add_marker(skip_marker)
