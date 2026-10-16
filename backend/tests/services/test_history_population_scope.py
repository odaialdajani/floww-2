"""New recorded selectors must retain requested strike-population depth."""
from unittest.mock import patch

import duckdb
import pytest

import server
from services.price_node_history import scope_id
from tests.offline_network import deny_external_network  # noqa: F401
from tests.solstice.test_r14_window_producer import produce


@pytest.mark.asyncio
async def test_actual_recorded_history_scopes_separate_80_and_200_strike_populations(deny_external_network):
    build = server._build_heatmap_impl
    selectors = []
    for depth in (80, 200):
        async def with_depth(*args, _depth=depth, **kwargs):
            return await build(*args, **{**kwargs, "max_strikes": _depth})

        with duckdb.connect(":memory:") as conn, patch.object(server, "_build_heatmap_impl", side_effect=with_depth):
            payload = await produce(conn, baseline=False)
            stored = conn.execute("SELECT query_key,expiries,formula_version,exposure_basis FROM heatmap_snapshots_v2 WHERE snapshot_id=?", [payload["snapshotId"]])
            row = dict(zip([c[0] for c in stored.description], stored.fetchone(), strict=True))
            assert payload["history_scope"] == scope_id(row)
            assert payload["map_query"]["maxStrikes"] == depth
            selectors.append(payload["history_scope"])
    assert selectors[0] != selectors[1], "Different requested strike populations must not share a node-history selector"
