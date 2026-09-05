import sys, os, json, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from services.public_api_adapter import _normalize_bars, _session_label, _as_int, _as_float, fetch_bars_from_public_api

print("=== 1. unknown session bucket key -> labelled 'regular' ===")
for k in ["overnightMarket", "twentyFourHour", "OVERNIGHT", "eveningSession", "unknownThing", "postMarket"]:
    print(f"  _session_label({k!r}) -> {_session_label(k)!r}")

payload = {
  "regularMarket": {"bars": [{"timestamp": "2026-09-03T20:00:00Z", "open":500.0,"high":505.0,"low":499.0,"close":503.0,"volume":1000}]},
  "overnightMarket": {"bars": [{"timestamp": "2026-09-04T04:00:00Z", "open":600.0,"high":600.0,"low":600.0,"close":600.0,"volume":3}]},
}
out = _normalize_bars(payload, 100, sessions="regular")
print("  sessions='regular' rows:", [(b["date"], b["session"], b["close"]) for b in out])

print()
print("=== 2. top-level 'bars' list collides with regularMarket bucket (last writer wins) ===")
p2 = {
  "bars": [{"timestamp": "2026-09-03T20:00:00Z", "close": 111.0, "volume": 1}],
  "regularMarket": {"bars": [{"timestamp": "2026-09-03T20:00:00Z", "close": 999.0, "volume": 2}]},
}
print("  ", _normalize_bars(p2, 100))

print()
print("=== 3. NaN / Infinity survive _as_float; Starlette renders with allow_nan=False ===")
p3 = {"regularMarket": {"bars": [{"timestamp":"2026-09-03T20:00:00Z","open":"NaN","high":"Infinity","low":1.0,"close":2.0,"volume":5}]}}
rows = _normalize_bars(p3, 100)
print("  rows:", rows)
try:
    json.dumps(rows, allow_nan=False)
    print("  json.dumps(allow_nan=False): OK")
except ValueError as e:
    print("  json.dumps(allow_nan=False) RAISED:", type(e).__name__, e)

print()
print("=== 4. _as_int(inf) -> uncaught OverflowError ===")
try:
    _as_int(float("inf"))
    print("  no raise")
except Exception as e:
    print("  RAISED:", type(e).__name__, e)

print()
print("=== 5. string sort of timestamps ===")
mixed = {"regularMarket": {"bars": [
    {"timestamp": 1757016000, "close": 1.0},      # epoch seconds int
    {"timestamp": 999999999,  "close": 2.0},      # 9-digit epoch (2001-09-08)
]}}
print("  epoch-int mix ->", [(b["date"], b["close"]) for b in _normalize_bars(mixed, 100)])
mixed2 = {"regularMarket": {"bars": [
    {"timestamp": "2026-09-03T09:30:00-04:00", "close": 1.0},
    {"timestamp": "2026-09-03T13:31:00Z",      "close": 2.0},   # = 09:31 EDT, later
]}}
print("  offset/Z mix ->", [(b["date"], b["close"]) for b in _normalize_bars(mixed2, 100)])
dup = {"regularMarket": {"bars": [
    {"timestamp": "2026-09-03T20:00:00Z",     "close": 1.0},
    {"timestamp": "2026-09-03T20:00:00.000Z", "close": 1.0},
]}}
print("  same instant, 2 spellings ->", len(_normalize_bars(dup, 100)), "rows (dedup by raw string)")

print()
print("=== 6. httpx timeout is NOT caught by `except TimeoutError` -> no failure telemetry ===")
recorded = []
async def probe():
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="a")
    broker.get_bars = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
    with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=broker)), \
         patch("services.public_api_adapter._record_call", side_effect=lambda ok: recorded.append(ok)):
        r = await fetch_bars_from_public_api("SPY")
    return r
print("  result:", asyncio.run(probe()), "| _record_call invocations:", recorded)

print()
print("=== 7. payload with ONLY extended-hours buckets under default sessions='regular' ===")
p7 = {"preMarket": {"bars":[{"timestamp":"2026-09-04T12:00:00Z","close":1.0}]},
      "afterHours":{"bars":[{"timestamp":"2026-09-03T22:00:00Z","close":2.0}]}}
print("  normalized rows:", _normalize_bars(p7, 100))

print()
print("=== 8. bar with every OHLC field missing still ships as a bar ===")
p8 = {"regularMarket": {"bars": [{"timestamp": "2026-09-03T20:00:00Z"}]}}
print("  ", _normalize_bars(p8, 100))
