"""Offline synthetic stored-route fixture. No production capture/restart proof."""

import asyncio
import json
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import duckdb  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from routes import solstice_price_paths as routes  # noqa: E402
from services.heatmap_history import record_range_envelope  # noqa: E402


async def generate():
    fixtures = ROOT / "docs/solstice/r18/fixtures"
    envelopes = [json.loads((fixtures / name).read_text()) for name in (
        "complete_v1.json", "partial_skipped_v1.json",
    )]
    conn = duckdb.connect(":memory:")
    try:
        for envelope in envelopes:
            receipt = record_range_envelope(conn, envelope)
            if receipt.get("status") != "recorded":
                raise AssertionError(receipt)
        app = FastAPI()
        app.include_router(routes.router)
        transport = ASGITransport(app=app)
        with patch.object(routes, "_store_conn", return_value=conn), patch.object(
            socket, "create_connection", side_effect=AssertionError("Offline fixture refuses network")
        ):
            async with AsyncClient(transport=transport, base_url="http://offline.local") as client:
                base = "/api/solstice/price-paths/range-records"
                params = dict(ticker="SPY", min_dte=14, max_dte=60, limit=50, offset=0)
                response = await client.get(base, params=params)
                response.raise_for_status()
                result = dict(version="floww-range-transport-fixture.v1", synthetic=True,
                              qualification="pending", source_commit=subprocess.check_output(
                                  ["git", "--no-pager", "rev-parse", "HEAD"], cwd=ROOT, text=True
                              ).strip(), index=response.json(), records={})
                for envelope in envelopes:
                    response = await client.get(base + "/" + envelope["record_id"])
                    response.raise_for_status()
                    body = response.json()
                    if body["envelope"] != envelope:
                        raise AssertionError("Stored route did not restore the actual envelope")
                    result["records"][envelope["record_id"]] = body
                missing = await client.get(base + "/rga1-" + "0" * 24)
                if missing.status_code != 404:
                    raise AssertionError(missing.text)
                result["missing"] = missing.json()
                conn.execute("UPDATE range_analytics_envelopes_v1 SET envelope_json = ? WHERE record_id = ?",
                             ["{corrupt", envelopes[0]["record_id"]])
                corrupt = await client.get(base + "/" + envelopes[0]["record_id"])
                if corrupt.status_code != 422:
                    raise AssertionError(corrupt.text)
                result["corrupt"] = corrupt.json()
                conn.execute("DELETE FROM range_analytics_envelopes_v1")
                response = await client.get(base, params=params)
                response.raise_for_status()
                result["empty"] = response.json()
        destination = ROOT / "frontend/src/fixtures/integration/range-analytics.v1/replay-transport.json"
        destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(dict(status="passed_offline_synthetic_stored_routes", records=len(result["records"]),
                              missing=missing.status_code, corrupt=corrupt.status_code,
                              output=str(destination.relative_to(ROOT)))))
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(generate())
