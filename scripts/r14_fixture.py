"""Finite offline vertical-slice fixture exporter. Never starts the application lifespan."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def generate(ticker="SPY", spot=100, expiry_scope="loaded"):
    import duckdb
    from fastapi.testclient import TestClient

    import server
    from services import cvserver_client, duckdb_engine
    from services.agent.display_map import display_facts
    from services.heatmap_history import list_decisions, replay_snapshot
    from services.solstice_replay import recorded_display

    now = datetime.now(UTC)
    expiries = [(now.date() + timedelta(days=i)).isoformat() for i in (2, 7, 14, 21, 28, 35)]
    contracts = []
    for ei, expiry in enumerate(expiries):
        for i in range(61):
            strike = spot - 15 + i * .5
            side = "put" if strike > spot else "call"
            oi = 100 if strike == spot else 10 + (i * 7 + ei * 13) % 70
            delta = None if strike == spot + 5 else (.5 if side == "call" else -.5)
            contracts.append(dict(osi=f"{ticker}{expiry.replace('-', '')[2:]}{'C' if side == 'call' else 'P'}{int(strike*1000):08d}",
                                  strike=strike, expiry=expiry, type=side, multiplier=100,
                                  multiplier_source="synthetic_contract_spec", oi=oi, volume=10, gamma=.1,
                                  delta=delta, iv=.25, theta=-.02, vega=.1, T=(datetime.fromisoformat(expiry).date() - now.date()).days / 365,
                                  bid=1, ask=1.1, last=1.05, bid_timestamp=now.isoformat(),
                                  ask_timestamp=now.isoformat(), last_timestamp=now.isoformat(),
                                  data_source="r14_fixture", received_at=(now-timedelta(seconds=2)).isoformat()))
    source = dict(ticker=ticker, spot=spot, expiries=expiries, contracts=contracts,
                  data_source="r14_fixture", event_time=(now-timedelta(seconds=60)).isoformat(),
                                    fetched_at=(now-timedelta(seconds=55)).isoformat(), received_at=(now-timedelta(seconds=55)).isoformat())
    store = TemporaryDirectory(prefix="r14-offline-fixture-")
    conn = duckdb.connect(str(Path(store.name) / "fixture.duckdb"))
    async def build():
        scope = {"expiry_scope": expiry_scope} if expiry_scope == "next" else {}
        out = await server._build_heatmap_impl(ticker, max_expiries=6, with_taps=False, **scope)
        pending = [task for task in server._background_tasks if task.get_loop() is asyncio.get_running_loop()]
        if pending:
            await asyncio.gather(*pending)
        return out
    server._BUILD_HEATMAP_CACHE.clear()
    with patch.object(cvserver_client, "CVSERVER_API_KEY", ""), \
         patch.object(duckdb_engine.db, "_conn", conn), \
         patch.object(server, "fetch_spot_and_chains_merged", AsyncMock(return_value=source)), \
         patch.object(server, "velocity_and_rolling", AsyncMock(return_value={"history": []})), \
         patch.object(server, "save_snapshot", AsyncMock(return_value=None)), \
         patch.object(server, "calc_realized_volatility", return_value=None), \
         patch.object(server, "calc_iv_rank_percentile", return_value={"iv_rank": None, "status": "unavailable"}), \
         patch("auth.get_api_key", return_value="r14-fixture-only"):
        for c in contracts:
            c.update(volume=0, received_at=source["fetched_at"], bid_timestamp=source["event_time"], ask_timestamp=source["event_time"], last_timestamp=source["event_time"])
        baseline = asyncio.run(build())
        server._BUILD_HEATMAP_CACHE.clear()
        source.update(event_time=(now-timedelta(seconds=5)).isoformat(), fetched_at=(now-timedelta(seconds=2)).isoformat(),
                      received_at=(now-timedelta(seconds=2)).isoformat())
        for c in contracts:
            c.update(volume=10, received_at=source["fetched_at"], bid_timestamp=source["event_time"], ask_timestamp=source["event_time"], last_timestamp=source["event_time"])
        out = asyncio.run(build())
        key = f"{spot:g}"
        scale = spot ** 2 / 100 ** 2
        assert out["grid"]["grid"][expiries[0]][key] == 100000 * scale
        assert out["metrics"]["grids"]["activity"]["grid"][expiries[0]][key] == 10000 * scale
        assert out["metrics"]["grids"]["session_delta_volume"]["grid"][expiries[0]][key] == 5000 * scale
        # HTTP route delivery, not a second renderer or hand-authored exposure engine.
        with patch.object(server, "build_heatmap", AsyncMock(return_value=out)):
            client = TestClient(server.app)  # no context-manager / no startup jobs
            display = client.get(f"/api/heatmap/{ticker}?expiries=6&withTaps=false").json()
        sid = out["snapshotId"]
        replay = replay_snapshot(conn, sid)
        target_expiry = out["expiries_used"][1 if len(out["expiries_used"]) > 1 else 0]
        target = next(c for c in contracts if c["strike"] == spot and c["expiry"] == target_expiry)
        detail = client.get(f"/api/solstice/{ticker}/contract", params={"osi": target["osi"], "snapshot_id": sid}).json()
        walls = out["metrics"]["walls"]
        wall = next((w for w in walls if spot in w.get("members", [])), walls[0] if walls else None)
        screen = dict(contextVersion=2, page="trinity", ticker=ticker, metric="gex", overlayMetric="raw", displayMode="live",
                      snapshotId=sid, provider=out["data_source"], formula=out["formula_version"], activePane="raw",
                      mapQuery=out["map_query"], mapVersion=out["asof"], mapStrikes=out["grid"]["strikes"],
                      mapExpiries=out["grid"]["expiries"], selectedStrike=spot, selectedExpiry=target_expiry,
                      selectedWall=wall["wall_id"] if wall else None)
        facts, gaps = display_facts(out, screen, ticker, datetime.now(UTC))
        recorded = recorded_display(replay, ticker, sid)
        prior = replay_snapshot(conn, baseline["snapshotId"])
        recorded["window_baseline"] = recorded_display(prior, ticker, baseline["snapshotId"])
        admissions = {}
        for family in ("contract", "window", "vex", "charm"):
            selector = {**screen, "page":"heatseeker", "activePane":"gex"}
            if family == "contract":
                selector.update(selectedContract={k:target[k] for k in ("osi","strike","expiry","type")})
            elif family == "window":
                selector.update(overlayMetric="window",windowBaselineId=baseline["snapshotId"],windowInterval=out["metrics"]["grids"]["window"]["interval"])
            else:
                selector.update(metric=family,displayMode="replay",recordedMetricVersion="metric-record.v1")
            ledger, limitations = display_facts(recorded,selector,ticker,datetime.now(UTC))
            assert ledger, (family, limitations)
            admissions[family] = dict(screen=selector,facts=ledger,gaps=limitations)
        assert out["metrics"]["grids"]["window"]["grid"][expiries[0]][key] == 5000 * scale
        decisions = list_decisions(conn, ticker)
        review = None
        if decisions:
            review = client.post(f"/api/solstice/{ticker}/decisions/{decisions[0]['decision_id']}/review",
                                 json={"state": "reviewed", "note": "synthetic R14 read-only review fixture"},
                                 headers={"X-API-Key": "r14-fixture-only"}).json()
        result = dict(note="Synthetic engineering fixture, not a market/participant/outcome observation",
                      display=display, replay=replay, contract=detail, screen=screen,
                      lodestar_facts=facts, gaps=gaps, decisions=decisions, review=review, baseline=prior, admissions=admissions)
    conn.close()
    store.cleanup()
    server._BUILD_HEATMAP_CACHE.clear()
    return server._sanitize(result)


def export():
    # Reuse the tested fail-closed transports, but never overwrite R11/R13 receipts.
    import socket

    import httpx

    from r13_fixture import ATTEMPTS, refuse, refuse_async

    ATTEMPTS.clear()
    original, original_ex = socket.socket.connect, socket.socket.connect_ex

    def local(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original(sock, address)
        refuse()

    def local_ex(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_ex(sock, address)
        refuse()

    with patch.object(socket.socket, "connect", local), patch.object(socket.socket, "connect_ex", local_ex), \
         patch.object(httpx.HTTPTransport, "handle_request", refuse), patch.object(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async):
        packet = generate()
        packet["secondary_display"] = generate("QQQ", 400)["display"]
        packet["next_display"] = generate(expiry_scope="next")["display"]
    assert not ATTEMPTS, "A provider seam was missed; blocked attempts cannot be swallowed"
    destination = ROOT / "docs/solstice/r14/evidence/vertical-fixture.json"
    destination.write_text(json.dumps(packet, indent=2, default=str, allow_nan=False) + "\n")
    print(f"Wrote {destination.relative_to(ROOT)}; provider transports blocked; source/recorded family ledgers verified; no lifespan")


if __name__ == "__main__":
    export()
