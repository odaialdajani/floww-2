"""Shared conftest for service-level tests.

Adds backend/ to sys.path so that ``from services.X import Y`` works
without each test file having its own sys.path.insert hack.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_backend_dir = Path(__file__).resolve().parent.parent  # backend/
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))


# ---------------------------------------------------------------------------
# Schwab streamer test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_token_manager():
    """Mock token manager that returns a fake token (injected into the streamer harness)."""
    tm = MagicMock()
    tm.get_access_token.return_value = "fake-access-token-12345"
    tm.is_expired.return_value = False
    tm.refresh_token = AsyncMock(return_value="refresh-token-67890")
    return tm


@pytest.fixture
def streamer(mock_token_manager):
    """Create a SchwabStreamer with mocked token manager."""
    from services.schwab_streamer import SchwabStreamer

    s = SchwabStreamer(token_manager=mock_token_manager)
    return s
