"""B18 alerts. Synthetic only."""
def test_evaluate_gates():
    from services.chart_alerts import evaluate
    assert evaluate({"replay": True}, {"price": 1, "role": "k"})["fired"] is False
    assert evaluate({"target": 100}, {"stale": True})["fired"] is False
    assert evaluate({"target": 100}, {"price": None, "role": "k"})["fired"] is False
    assert evaluate({"target": 100, "tick": 0.5}, {"price": 100.2, "role": "king"})["fired"] is True
    assert evaluate({"target": 100, "tick": 0.01}, {"price": 101, "role": "king"})["fired"] is False
