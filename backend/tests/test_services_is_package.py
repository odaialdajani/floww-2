"""Regression: backend/services must be importable as a regular package.

If this fails, someone deleted __init__.py — which breaks full pytest
collection and silently hides 20+ test files from CI.
"""
from pathlib import Path


def test_services_is_a_package():
    import services
    assert hasattr(services, "__file__"), \
        "services is a namespace package — __init__.py missing"


def test_services_ml_is_a_package():
    import services.ml
    assert hasattr(services.ml, "__file__"), \
        "services.ml is a namespace package — __init__.py missing"


def test_services_ml_exports_degenerate_model_error():
    from services.ml import DegenerateModelError
    assert issubclass(DegenerateModelError, Exception)


def test_services_init_file_on_disk():
    here = Path(__file__).resolve().parent  # backend/tests/
    init_path = here.parent / "services" / "__init__.py"
    assert init_path.is_file(), f"{init_path} missing"


def test_services_ml_init_file_on_disk():
    here = Path(__file__).resolve().parent  # backend/tests/
    init_path = here.parent / "services" / "ml" / "__init__.py"
    assert init_path.is_file(), f"{init_path} missing"


def test_inference_exports_class_labels():
    """The 3-class prediction system must be exported."""
    from services.ml.inference import CLASS_LABELS, DOWN, HOLD, UP
    assert CLASS_LABELS[UP] == "UP"
    assert CLASS_LABELS[DOWN] == "DOWN"
    assert CLASS_LABELS[HOLD] == "HOLD"


def test_duckdb_engine_exports_timeout_constant():
    """The DuckDB timeout constant must be configurable."""
    from services.duckdb_engine import QUERY_TIMEOUT_S
    assert isinstance(QUERY_TIMEOUT_S, float)
    assert QUERY_TIMEOUT_S > 0
