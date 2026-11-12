from auth import PUBLIC_PATHS, is_public_path
from services.agent.local_access import research_path


def test_no_bare_agent_prefix_public():
    assert not any(p.startswith("/api/agent") for p in PUBLIC_PATHS)


def test_actions_never_public():
    for path in ("/api/agent-actions/live/fire", "/api/agent/budget", "/api/agent/ask/extra"):
        assert not is_public_path(path)
        assert not research_path("POST", path)


def test_only_exact_research_methods_are_exempt():
    assert research_path("POST", "/api/agent/ask")
    assert not research_path("DELETE", "/api/agent/ask")
    assert not research_path("PUT", "/api/agent/ask")


def test_citation_reads_are_exempt_but_citation_writes_are_not():
    assert research_path("GET", "/api/agent/citations")
    assert research_path("GET", "/api/agent/citations/cit_" + "a" * 24)
    assert not research_path("POST", "/api/agent/citations")
    assert not research_path("PUT", "/api/agent/citations/cit_" + "a" * 24)
    assert not research_path("DELETE", "/api/agent/citations/cit_" + "a" * 24)
    assert not research_path("GET", "/api/agent/citations/not-an-id")
