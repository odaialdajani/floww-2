"""B13 workspaces. Synthetic only."""
def test_identity_discovery_and_isolation():
    from services.chart_workspaces import apply_revision, check_owner, discover_identity
    assert discover_identity({})["status"] == "unavailable"
    assert discover_identity({"principal": {"user_id": "u1"}})["status"] == "available"
    assert check_owner({"user_id": "u1"}, "u1", "u1") is True
    assert check_owner({"user_id": "u1"}, "u1", "u2") is False
    assert check_owner(None, "u1", "u1") is False
    assert check_owner({"user_id": "u1"}, "u2", "u2") is False
    stored = {"revision": 3, "name": "a"}
    assert apply_revision(stored, {"revision": 3})["status"] == "conflict"
    out = apply_revision(stored, {"revision": 4, "name": "b"})
    assert out["status"] == "ok" and out["workspace"]["name"] == "b"
