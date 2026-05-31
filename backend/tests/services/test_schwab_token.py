"""
backend/tests/services/test_schwab_token.py

Tests for Schwab OAuth token auto-refresh.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from schwab import SchwabTokenManager


class TestSchwabTokenManager:
    """Test token management and auto-refresh."""

    @pytest.fixture
    def token_path(self):
        """Create a temp token file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "access_token": "test_access",
                "refresh_token": "test_refresh",
                "expires_at": datetime.now(timezone.utc).timestamp() + 3600,
            }, f)
            f.flush()
            yield Path(f.name)
        os.unlink(f.name)

    @pytest.fixture
    def expired_token_path(self):
        """Create a temp token file with expired token."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "access_token": "test_access",
                "refresh_token": "test_refresh",
                "expires_at": datetime.now(timezone.utc).timestamp() - 100,
            }, f)
            f.flush()
            yield Path(f.name)
        os.unlink(f.name)

    def test_load_valid_token(self, token_path):
        tm = SchwabTokenManager(token_path=token_path)
        token = tm.load()
        assert token is not None
        assert token["access_token"] == "test_access"

    def test_is_expired_false(self, token_path):
        tm = SchwabTokenManager(token_path=token_path)
        assert tm.is_expired() is False

    def test_is_expired_true(self, expired_token_path):
        tm = SchwabTokenManager(token_path=expired_token_path)
        assert tm.is_expired() is True

    def test_get_access_token_valid(self, token_path):
        tm = SchwabTokenManager(token_path=token_path)
        token = tm.get_access_token()
        assert token == "test_access"

    def test_get_access_token_expired(self, expired_token_path):
        tm = SchwabTokenManager(token_path=expired_token_path)
        # Should return None (needs refresh, which is async)
        token = tm.get_access_token()
        assert token is None

    def test_get_access_token_no_file(self):
        tm = SchwabTokenManager(token_path=Path("/nonexistent/token.json"))
        assert tm.get_access_token() is None

    def test_save_token(self, token_path):
        tm = SchwabTokenManager(token_path=token_path)
        new_token = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_at": datetime.now(timezone.utc).timestamp() + 7200,
        }
        tm.save(new_token)
        loaded = tm.load()
        assert loaded["access_token"] == "new_access"

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, expired_token_path):
        """Token refresh should work with mocked OAuth endpoint."""
        tm = SchwabTokenManager(token_path=expired_token_path)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "refreshed_access",
            "refresh_token": "refreshed_refresh",
            "expires_in": 1800,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value.post.return_value = mock_response
            mock_ctx.__aexit__.return_value = None
            mock_client.return_value = mock_ctx

            # Need to set env vars for client ID/secret
            with patch.dict(os.environ, {"SCHWAB_CLIENT_ID": "test", "SCHWAB_CLIENT_SECRET": "test"}):
                result = await tm.refresh_token()

        assert result == "refreshed_access"
        # Verify token was saved
        loaded = tm.load()
        assert loaded["access_token"] == "refreshed_access"

    @pytest.mark.asyncio
    async def test_refresh_token_failure(self, expired_token_path):
        """Token refresh failure should return None gracefully."""
        tm = SchwabTokenManager(token_path=expired_token_path)

        with patch("httpx.AsyncClient") as mock_client:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__.return_value.post.side_effect = Exception("Network error")
            mock_ctx.__aexit__.return_value = None
            mock_client.return_value = mock_ctx

            with patch.dict(os.environ, {"SCHWAB_CLIENT_ID": "test", "SCHWAB_CLIENT_SECRET": "test"}):
                result = await tm.refresh_token()

        assert result is None

    def test_token_file_permissions(self, token_path):
        """Token file should be readable."""
        tm = SchwabTokenManager(token_path=token_path)
        tm.load()
        # File should exist and be readable
        assert token_path.exists()
        content = token_path.read_text()
        assert "access_token" in content
