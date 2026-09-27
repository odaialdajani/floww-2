"""RCE-guard tests (audit V2, Critical #4, High #9).

- POST /api/anomaly/{ticker}/load: model_path must stay inside the model
  dir (403 on traversal) and use a checkpoint suffix (422 otherwise).
- POST /api/turboquant/generate: model_name must be well-formed (422)
  and allowlisted (403); remote code execution stays off.
- POST /api/auth/dev-token: refuses with 403 unless FLOWW_ALLOW_DEV_TOKENS=1.

All offline. No torch / transformers / network required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from server import app

client = TestClient(app)

KEY = {"X-API-Key": "test-secret-key"}  # matches backend/tests/conftest.py


class TestAnomalyLoadPathGuard:
    def test_traversal_rejected_403(self):
        r = client.post(
            "/api/anomaly/SPY/load",
            headers=KEY,
            params={"model_path": "/etc/passwd"},
        )
        assert r.status_code == 403, r.text

    def test_relative_traversal_rejected_403(self):
        r = client.post(
            "/api/anomaly/SPY/load",
            headers=KEY,
            params={"model_path": "../../server.py"},
        )
        assert r.status_code == 403, r.text

    def test_bad_suffix_rejected_422(self):
        r = client.post(
            "/api/anomaly/SPY/load",
            headers=KEY,
            params={"model_path": "evil.py"},
        )
        assert r.status_code == 422, r.text

    def test_missing_checkpoint_404_not_500(self):
        r = client.post(
            "/api/anomaly/SPY/load",
            headers=KEY,
            params={"model_path": "does-not-exist.pt"},
        )
        # 404 when torch is absent the availability check fires first;
        # either way it must not attempt deserialization (no 500).
        assert r.status_code in (404, 503), r.text


class TestTurboQuantModelGate:
    def test_malformed_name_422(self):
        r = client.post("/api/turboquant/generate", headers=KEY, json={
            "prompt": "hi", "model_name": "not-a-model-id",
        })
        assert r.status_code == 422, r.text

    def test_non_allowlisted_403(self):
        r = client.post("/api/turboquant/generate", headers=KEY, json={
            "prompt": "hi", "model_name": "evil-org/evil-model",
        })
        assert r.status_code == 403, r.text

    def test_default_model_passes_gate(self):
        # Gate passes → falls through to the service check (503 here).
        # What matters: NOT 403/422.
        with patch("services.turboquant_cache.get_turboquant_service") as svc:
            svc.return_value = MagicMock(available=False)
            r = client.post("/api/turboquant/generate", headers=KEY, json={
                "prompt": "hi", "model_name": "Qwen/Qwen2.5-3B-Instruct",
            })
        assert r.status_code == 503, r.text

    def test_allowlist_env_admits_extra_model(self, monkeypatch):
        monkeypatch.setenv("FLOWW_LLM_MODEL_ALLOWLIST", "my-org/my-model")
        with patch("services.turboquant_cache.get_turboquant_service") as svc:
            svc.return_value = MagicMock(available=False)
            r = client.post("/api/turboquant/generate", headers=KEY, json={
                "prompt": "hi", "model_name": "my-org/my-model",
            })
        assert r.status_code == 503, r.text


class TestDevTokenGate:
    def test_minting_disabled_403(self, monkeypatch):
        monkeypatch.delenv("FLOWW_ALLOW_DEV_TOKENS", raising=False)
        r = client.post("/api/auth/dev-token", json={"email": "a@b.c"})
        assert r.status_code == 403, r.text

    def test_minting_armed_issues_token(self, monkeypatch):
        monkeypatch.setenv("FLOWW_ALLOW_DEV_TOKENS", "1")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
        r = client.post("/api/auth/dev-token",
                        json={"email": "Dev@Local", "tier": "pro"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["access_token"].count(".") == 2  # header.payload.sig
        assert body["subscriber"]["email"] == "dev@local"
