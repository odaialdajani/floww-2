from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


def test_empty_vendor_display_is_not_usable():
    from server import _display_quality
    quality = _display_quality("OI", "vendor-supplied-greeks", [])
    assert quality["state"] == "unavailable"
    assert quality["setupEligible"] is False


@pytest.mark.parametrize("extra", [{}, {"oi_trend_source": "lifecycle"}, {"oi_observations": [{}, {}]}])
def test_unobserved_open_interest_never_claims_positioning(extra):
    from services.heatseeker import classify_nodes
    result = classify_nodes([dict(strike=500, gamma_sign="positive", oi_trend="growing", **extra)])
    assert result["nodes"][0]["classification"] == "unknown"
    assert result["real_count"] == 0


def test_review_storage_failure_is_not_success(monkeypatch):
    import services.duckdb_engine as engine
    import services.heatmap_history as history
    from routes.solstice_review import register_review_routes
    monkeypatch.setattr(engine, "db", SimpleNamespace(conn=object()))
    monkeypatch.setattr(history, "save_decision_review", lambda *a, **kw: None)
    app = FastAPI()
    router = APIRouter()
    register_review_routes(router)
    app.include_router(router)
    result = TestClient(app).post("/SPY/decisions/missing/review", json={"state": "reviewed"})
    assert result.status_code == 503
    assert result.json()["detail"]["durability"] == "failed"


@pytest.mark.parametrize("ticker,decision", [("QQQ", "spy-decision"), ("SPY", "missing")])
def test_review_cannot_attach_to_another_ticker_or_missing_decision(monkeypatch, ticker, decision):
    import duckdb

    import services.duckdb_engine as engine
    from routes.solstice_review import register_review_routes
    from services.heatmap_history import ensure_tables

    conn = duckdb.connect(":memory:")
    try:
        ensure_tables(conn)
        conn.execute("INSERT INTO scenario_decisions_v1 (decision_id, ticker) VALUES (?, ?)",
                     ["spy-decision", "SPY"])
        monkeypatch.setattr(engine, "db", SimpleNamespace(conn=conn))
        app = FastAPI()
        router = APIRouter()
        register_review_routes(router)
        app.include_router(router)
        result = TestClient(app).post(f"/{ticker}/decisions/{decision}/review", json={"state": "reviewed"})
        assert result.status_code == 503
        assert conn.execute("SELECT count(*) FROM decision_reviews_v1").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize("context", [{"displayMode": "replay"}, {"overlayMetric": "activity"}, {"overlayMetric": "delta"}])
def test_unsupported_research_surface_cannot_fall_back_to_live_raw(context):
    from services.agent.contracts import request_spec
    with pytest.raises(ValueError, match="display"):
        request_spec({"question": "Explain this chart", "screen": {"ticker": "SPY", **context}})
