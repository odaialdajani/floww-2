import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ["TESTING"] = "1"
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from server import app
client = TestClient(app, raise_server_exceptions=False)

def broker_with(payload):
    b = MagicMock()
    b.get_trading_account.return_value = MagicMock(account_id="a")
    b.get_bars = AsyncMock(return_value=payload)
    return b

print("=== A. payload with ONLY extended-hours buckets, default sessions=regular ===")
p = {"preMarket": {"bars":[{"timestamp":"2026-09-04T12:00:00Z","open":1,"high":1,"low":1,"close":1,"volume":9}]}}
with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=broker_with(p))):
    r = client.get("/api/public/bars/SPY?timeframe=5Min")
print("  status:", r.status_code, "body:", r.text[:200])

print()
print("=== B. vendor returns NaN in a bar ===")
p = {"regularMarket": {"bars":[{"timestamp":"2026-09-03T20:00:00Z","open":"NaN","high":2,"low":1,"close":2,"volume":9}]}}
with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=broker_with(p))):
    try:
        r = client.get("/api/public/bars/SPY")
        print("  status:", r.status_code, "body:", r.text[:200])
    except Exception as e:
        print("  EXCEPTION escaped to server:", type(e).__name__, e)

print()
print("=== C. vendor returns Infinity volume ===")
p = {"regularMarket": {"bars":[{"timestamp":"2026-09-03T20:00:00Z","open":1,"high":2,"low":1,"close":2,"volume":float('inf')}]}}
with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=broker_with(p))):
    try:
        r = client.get("/api/public/bars/SPY")
        print("  status:", r.status_code, "body:", r.text[:200])
    except Exception as e:
        print("  EXCEPTION escaped to server:", type(e).__name__, e)

print()
print("=== D. junk / hostile ticker reaches the vendor symbol untouched ===")
seen = []
b = MagicMock(); b.get_trading_account.return_value = MagicMock(account_id="a")
async def cap(sym, period, aggregation=None, **kw):
    seen.append(sym); return {"regularMarket": {"bars": []}}
b.get_bars = cap
with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=b)):
    for t in ["SPY", "a"*300, "'; DROP--", "<script>", "..%5C..", "SPY%20OR%201=1"]:
        r = client.get(f"/api/public/bars/{t}")
print("  symbols forwarded to Public.com:", [s[:40] + ("..." if len(s)>40 else "") for s in seen])

print()
print("=== E. quotes single-result fallback returns another symbol's price under the requested ticker ===")
with patch("routes.public_api.fetch_quotes_from_public_api",
           new=AsyncMock(return_value={"QQQ": {"spot": 400.0, "last": 400.0, "ticker": "QQQ"}})):
    r = client.get("/api/public/quotes/SPY")
print("  GET /api/public/quotes/SPY ->", r.status_code, r.json())

print()
print("=== F. quote with no bid/ask/last -> spot 0.0 with ok:true ===")
q = MagicMock(); q.symbol="SPY"; q.bid=None; q.ask=None; q.last=None; q.mid_price=None
for f in ("bid_size","ask_size","volume","previous_close","change","percent_change","timestamp"):
    setattr(q, f, None)
b2 = MagicMock(); b2.get_trading_account.return_value = MagicMock(account_id="a")
b2.get_quotes = AsyncMock(return_value=[q])
with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=b2)):
    r = client.get("/api/public/quotes/SPY")
print("  ->", r.status_code, r.json())

print()
print("=== G. limit far above what the period can supply, silently ===")
p = {"regularMarket": {"bars":[{"timestamp":f"2026-09-{d:02d}T20:00:00Z","open":1,"high":2,"low":1,"close":2,"volume":9} for d in range(1,6)]}}
with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=broker_with(p))):
    r = client.get("/api/public/bars/SPY?timeframe=1Day&limit=5000")
print("  asked 5000 daily bars ->", r.status_code, "count:", r.json().get("count"), "no warning field:", "warning" not in r.json())

print()
print("=== H. timeframe echoed back raw ===")
with patch("routes.public_api.fetch_bars_from_public_api", new=AsyncMock(return_value=[{"date":"x"}])):
    r = client.get("/api/public/bars/SPY?timeframe=%20%201dAy%20")
print("  ->", r.status_code, "echoed timeframe:", repr(r.json().get("timeframe")))
