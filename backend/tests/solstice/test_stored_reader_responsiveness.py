"""Stored reads must not prevent the API loop from serving other work."""
import asyncio
import threading
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("reader", ["capability", "replay", "wall_curve"])
async def test_stored_reader_allows_loop_progress_while_read_waits(monkeypatch, reader):
    from routes import solstice
    from services import connection_guard, duckdb_engine, heatmap_history, solstice_wall_curve

    monkeypatch.setattr(duckdb_engine, "db", SimpleNamespace(conn=object()))
    progress = threading.Event()
    observed = []

    def wait_for_other_request(*args, **kwargs):
        # This callback represents unrelated work already queued on the loop.
        # It cannot execute while the route blocks that loop synchronously.
        observed.append(progress.wait(timeout=0.3))
        return [] if reader == "capability" else {"status": "ok"}

    asyncio.get_running_loop().call_soon(progress.set)
    if reader == "capability":
        monkeypatch.setattr(connection_guard, "query_rows", wait_for_other_request)
        await solstice.capability()
    elif reader == "replay":
        monkeypatch.setattr(heatmap_history, "replay_snapshot", wait_for_other_request)
        await solstice.replay("saved-id")
    else:
        monkeypatch.setattr(solstice_wall_curve, "wall_curve", wait_for_other_request)
        await solstice.wall_curve_route("SPY", wall_id="wall", metric_id="dadgex_net_v1",
                                       query_key="stored-scope", as_of=None, day=None, limit=200)
    assert observed == [True], "the stored read prevented unrelated API loop work"
