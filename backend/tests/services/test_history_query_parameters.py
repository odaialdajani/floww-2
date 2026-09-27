import duckdb

from services import heatmap_history as h
from services.solstice_labels import close_episodes


def test_escaped_strings_stay_data():
    c = duckdb.connect(":memory:")
    h.ensure_tables(c)
    evil = "SPY'; DROP TABLE decision_reviews_v1; --"
    did = h.record_decision(c, {"ticker": evil, "features": {}})
    assert h.save_decision_review(c, did, "reviewed", reason=evil, note=evil, ticker=evil)
    assert c.execute("SELECT reason,note FROM decision_reviews_v1").fetchone() == (evil, evil)
    assert len(h.list_decisions(c, evil)) == 1
    assert h.list_decisions(c, "' OR 1=1 --") == []
    c.close()


def test_untyped_limit_cannot_execute_statements():
    c = duckdb.connect(":memory:")
    h.ensure_tables(c)
    c.execute("CREATE TABLE probe(value INTEGER)")
    c.execute("INSERT INTO probe VALUES (1)")
    h.list_decisions(c, "SPY", limit="1; DELETE FROM probe; --")
    assert c.execute("SELECT count(*) FROM probe").fetchone() == (1,)
    c.close()


def test_stored_policy_cannot_delete_unrelated_outcomes():
    c = duckdb.connect(":memory:")
    h.ensure_tables(c)
    policy = "x' OR 1=1 --"
    did = h.record_decision(
        c,
        {
            "ticker": "SPY",
            "features": {"zone": [99, 101], "target": 103, "stop": 97, "horizon_s": 60, "policy_version": policy},
        },
    )
    h.record_outcome(c, did, "SPY", 60, "indeterminate", censored=True, detail={"path_end_t": 0}, policy_version=policy)
    h.record_outcome(c, "unrelated", "QQQ", 60, "target_hit", policy_version="safe")
    assert c.execute("SELECT count(*) FROM outcome_labels_v1 WHERE decision_id='unrelated'").fetchone() == (1,)
    close_episodes(c, {did: [(1, 100), (61, 103)]})
    assert c.execute("SELECT count(*) FROM outcome_labels_v1 WHERE decision_id='unrelated'").fetchone() == (1,)
    c.close()
