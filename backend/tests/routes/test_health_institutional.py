"""
Standalone test for the institutional health section (Agent D, D5/C11):
feed x budget tokens x sweep age x alert counts x calibration stage.
Unknown-tolerant: unwired sources report None + note, never fabricated.
"""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from routes.health import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _inst():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "institutional" in data, "health must carry the C11 institutional section"
    return data["institutional"]


class TestInstitutionalHealth:
    def test_section_keys(self):
        inst = _inst()
        for key in ("feed", "budget", "sweep", "alerts", "calibration"):
            assert key in inst, f"institutional missing key: {key}"

    def test_sweep_age_unknown_until_hooked(self):
        from services import sweep_watch

        sweep_watch._reset()
        inst = _inst()
        assert inst["sweep"]["age_s"] is None
        sweep_watch.note_sweep()
        inst2 = _inst()
        assert inst2["sweep"]["age_s"] is not None
        assert inst2["sweep"]["age_s"] >= 0
        sweep_watch._reset()

    def test_budget_section_honest(self):
        inst = _inst()
        assert inst["budget"].get("status") in ("ok", "unknown")

    def test_calibration_never_fabricated(self):
        inst = _inst()
        stage = inst["calibration"].get("stage")
        assert stage is None or isinstance(stage, int)
