"""S04 lease protects external effect: failed-first fake-transport probes.

Lease loss before the effect must refuse WITHOUT broker placement.
Positive path places exactly once. No live calls.
"""
import sys

sys.path.insert(0, "backend")


def _tmp_lease(tmp_path, name="effect.lock"):
    return str(tmp_path / name)


def test_lease_loss_before_effect_places_zero(tmp_path):
    from services import execution_lease as lease

    path = _tmp_lease(tmp_path)
    acquired = lease.acquire_lease(path, "owner-a", 60.0)
    assert acquired.get("ok") is True
    token = acquired["token"]
    # Simulate loss before effect: release (crash/takeover) drops ownership.
    assert lease.release_lease(path, token)["ok"] is True
    calls = []

    def effect():
        calls.append("place")
        return {"order_id": "oid-1"}

    out = lease.effect_with_lease(path, token, 60.0, effect)
    assert out.get("ok") is False and out.get("reason") == "FENCED_OUT"
    assert calls == []


def test_lease_held_effect_places_once(tmp_path):
    from services import execution_lease as lease

    path = _tmp_lease(tmp_path)
    acquired = lease.acquire_lease(path, "owner-a", 60.0)
    assert acquired.get("ok") is True
    token = acquired["token"]
    calls = []

    def effect():
        calls.append("place")
        return {"order_id": "oid-1"}

    try:
        out = lease.effect_with_lease(path, token, 60.0, effect)
        assert out.get("ok") is True
        assert calls == ["place"]
    finally:
        lease.release_lease(path, token)


def test_fenced_action_releases_and_blesses_only_when_held(tmp_path):
    from services import execution_lease as lease

    path = _tmp_lease(tmp_path)
    calls = []

    def effect():
        calls.append("place")
        return 42

    out = lease.fenced_action(path, "owner-a", 60.0, effect)
    assert out.get("ok") is True and out.get("result") == 42
    assert calls == ["place"]
    # Lease released afterward: path absent.
    assert lease.read_lease(path).get("present") is False
