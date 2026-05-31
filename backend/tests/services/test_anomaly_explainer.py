"""
backend/tests/services/test_anomaly_explainer.py

Unit tests for anomaly_explainer.py — NL explanation generation.

Coverage:
    - AnomalyExplainer initialization
    - VPIN spike detection and explanation
    - Quote Imbalance analysis
    - Regime-aware explanations
    - Confidence scoring
    - Message formatting
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_explainer_basic():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    # Feed some history
    for i in range(50):
        explainer.update(vpin=0.3 + i * 0.001, qi=0.1)
    result = explainer.explain(
        {"regime": "active", "zscore": 2.5, "anomaly_score": 0.05},
        {"vpin": 0.75, "quote_imbalance": -0.6, "queue_depth": 2000}
    )
    assert result.title
    assert result.summary
    assert result.confidence > 0
    assert result.regime == "active"


def test_explainer_vpin_spike():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    # Establish low baseline
    for _ in range(50):
        explainer.update(vpin=0.2, qi=0.05)
    # Now explain a spike
    result = explainer.explain(
        {"regime": "urgent", "zscore": 4.0, "anomaly_score": 0.08},
        {"vpin": 0.85, "quote_imbalance": -0.7}
    )
    assert "spike" in result.summary.lower() or "toxicity" in result.summary.lower()
    assert any("VPIN" in d for d in result.details)
    assert result.confidence > 0.3


def test_explainer_critical_title():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    for _ in range(50):
        explainer.update(vpin=0.2, qi=0.05)
    result = explainer.explain(
        {"regime": "urgent", "zscore": 5.0, "anomaly_score": 0.1},
        {"vpin": 0.9, "quote_imbalance": -0.8}
    )
    assert "CRITICAL" in result.title


def test_explainer_qi_divergence():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    for _ in range(50):
        explainer.update(vpin=0.3, qi=0.05)
    result = explainer.explain(
        {"regime": "active", "zscore": 3.0, "anomaly_score": 0.04},
        {"vpin": 0.5, "quote_imbalance": -0.65}
    )
    assert any("imbalance" in d.lower() or "sell" in d.lower() for d in result.details)


def test_explainer_calm_regime():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    for _ in range(50):
        explainer.update(vpin=0.15, qi=0.02)
    result = explainer.explain(
        {"regime": "calm", "zscore": 3.5, "anomaly_score": 0.03},
        {"vpin": 0.45, "quote_imbalance": 0.3}
    )
    assert any("calm" in f.lower() for f in result.contributing_factors)


def test_explainer_confidence_range():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    for _ in range(50):
        explainer.update(vpin=0.3, qi=0.1)
    result = explainer.explain(
        {"regime": "active", "zscore": 2.0, "anomaly_score": 0.05},
        {"vpin": 0.5, "quote_imbalance": 0.2}
    )
    assert 0.0 <= result.confidence <= 1.0


def test_explainer_to_message():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    for _ in range(50):
        explainer.update(vpin=0.3, qi=0.1)
    result = explainer.explain(
        {"regime": "active", "zscore": 2.0, "anomaly_score": 0.05},
        {"vpin": 0.5, "quote_imbalance": 0.2}
    )
    msg = result.to_message()
    assert result.title in msg
    assert "Regime:" in msg
    assert "Action:" in msg


def test_explainer_to_dict():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    for _ in range(50):
        explainer.update(vpin=0.3, qi=0.1)
    result = explainer.explain(
        {"regime": "active", "zscore": 2.0, "anomaly_score": 0.05},
        {"vpin": 0.5, "quote_imbalance": 0.2}
    )
    d = result.to_dict()
    assert "title" in d
    assert "summary" in d
    assert "confidence" in d
    assert "raw_data" in d


def test_explainer_system_context():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    for _ in range(50):
        explainer.update(vpin=0.3, qi=0.1)
    result = explainer.explain(
        {"regime": "active", "zscore": 2.0, "anomaly_score": 0.05},
        {"vpin": 0.5, "quote_imbalance": 0.2, "queue_depth": 8000, "ws_connections": 0}
    )
    assert any("queue" in f.lower() or "WebSocket" in f for f in result.contributing_factors)


def test_explainer_recommended_action_urgent():
    from services.anomaly_explainer import AnomalyExplainer
    explainer = AnomalyExplainer()
    for _ in range(50):
        explainer.update(vpin=0.2, qi=0.05)
    result = explainer.explain(
        {"regime": "urgent", "zscore": 5.0, "anomaly_score": 0.1},
        {"vpin": 0.85, "qi": -0.6}
    )
    assert "PAUTIOUS" in result.recommended_action or "reducing" in result.recommended_action.lower()
