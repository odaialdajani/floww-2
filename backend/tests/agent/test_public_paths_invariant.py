"""Public-paths invariant (plan v3 L8): no PUBLIC_PATHS entry parents a
mutating route outside the allow-list; agent-actions is never public."""

from auth import PUBLIC_PATHS, is_public_path


def test_no_bare_agent_prefix_public():
    assert "/api/agent/" not in PUBLIC_PATHS
    assert "/api/agent" not in PUBLIC_PATHS


def test_actions_never_public():
    assert is_public_path("/api/agent-actions/live/fire") is False
    assert is_public_path("/api/agent-actions/paper/stage") is False


def test_agent_read_routes_public():
    for p in ("/api/agent/ask", "/api/agent/stream/", "/api/agent/turn/", "/api/agent/cancel/", "/api/agent/budget", "/api/agent/claims", "/api/agent/prefs"):
        assert p in PUBLIC_PATHS, f"missing public route {p}"
