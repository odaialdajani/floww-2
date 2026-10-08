"""Dashboard polling must not consume the independent mutating request budget."""
import pytest
from starlette.requests import Request
from starlette.responses import Response

import server


@pytest.fixture(autouse=True)
def isolated_budget(monkeypatch):
    monkeypatch.setattr(server, "_TEST_MODE", False)
    monkeypatch.setattr(server, "RATE_LIMIT", 1)
    monkeypatch.setattr(server, "_rate_limits", {})


async def read(method, path):
    request = Request({"type": "http", "method": method, "path": path,
                       "headers": [], "client": ("203.0.113.44", 1234)})

    async def next_handler(_request):
        return Response(status_code=200)

    return await server.rate_limit_middleware(request, next_handler)


@pytest.mark.parametrize("path", [
    "/api/related/SPY", "/api/market/provider-updates", "/api/market/coverage",
    "/api/solstice/SPY/decisions", "/api/solstice/scan/leaderboard",
    "/api/ensemble/state", "/api/version",
])
async def test_dashboard_gets_do_not_block_each_other_or_mutations(path):
    assert (await read("GET", path)).status_code == 200
    assert (await read("GET", path)).status_code == 200
    assert (await read("POST", "/api/public/order")).status_code == 200
    assert (await read("POST", "/api/public/order")).status_code == 429


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_mutating_dashboard_requests_keep_the_limit(method):
    assert (await read(method, "/api/related/SPY")).status_code == 200
    assert (await read(method, "/api/related/SPY")).status_code == 429


async def test_unclassified_get_keeps_the_limit():
    assert (await read("GET", "/api/unclassified")).status_code == 200
    assert (await read("GET", "/api/unclassified")).status_code == 429


# Near-prefix lookalikes must NOT ride an admitted family name: the classifier
# matches on segment boundaries, so these stay subject to the burst limit.
@pytest.mark.parametrize("path", [
    "/api/spotlight", "/api/relatedness", "/api/heatmap2u", "/api/tickersXYZ",
    "/api/agentic/run", "/api/version2", "/api/chainmail", "/api/datastore",
])
async def test_near_prefix_lookalikes_keep_the_limit(path):
    assert (await read("GET", path)).status_code == 200
    assert (await read("GET", path)).status_code == 429


# Exact-family boundary: the family root itself is an admitted read, not only
# its children.
@pytest.mark.parametrize("path", [
    "/api/version", "/api/screener", "/api/related",
])
async def test_family_root_is_an_admitted_read(path):
    assert (await read("GET", path)).status_code == 200
    assert (await read("GET", path)).status_code == 200
    assert (await read("POST", "/api/public/order")).status_code == 200
    assert (await read("POST", "/api/public/order")).status_code == 429


# Broker/admission reads are never part of the exemption, even as GETs.
@pytest.mark.parametrize("path", [
    "/api/public/order", "/api/public/orders", "/api/alpaca/positions",
    "/admission/check",
])
async def test_broker_and_admission_gets_keep_the_limit(path):
    assert (await read("GET", path)).status_code == 200
    assert (await read("GET", path)).status_code == 429
