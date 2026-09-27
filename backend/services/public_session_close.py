"""Public daily close checked against the completed exchange session."""
import asyncio
import logging
import time
from collections import OrderedDict
from datetime import UTC, datetime
from weakref import WeakValueDictionary
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
_CACHE = OrderedDict()
_LOCKS = WeakValueDictionary()

async def completed_public_close(broker, symbol, now=None):
    from services.agent.access.horizon import horizon_window, required_close
    from services.market_provenance import timestamp
    from services.public_api_adapter import _extract_bars
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    try:
        if horizon_window('all', now=current)['session_state'] == 'open':
            return None
        closing = datetime.fromisoformat(required_close(current)).astimezone(UTC)
        # Allow the newly closed daily bar to settle before using it as a reference.
        if (current - closing).total_seconds() < 900:
            return None
        day = closing.astimezone(ZoneInfo('America/New_York')).date()
        key = (id(broker), symbol, closing.isoformat())
        # Strong local reference keeps this key alive while holders/waiters exist.
        lock = _LOCKS.setdefault(key, asyncio.Lock())
        async with lock:
            cached = _CACHE.get(key)
            if cached and cached[0] is broker and time.monotonic() - cached[1] < (300 if cached[2] else 30):
                return dict(cached[2]) if cached[2] else None
            result = None
            try:
                raw = await broker.get_bars(symbol, 'MONTH', 'EQUITY', 'ONE_DAY', trading_session_toggle='REGULAR_HOURS')
                if isinstance(raw, dict) and raw.get('symbol') == symbol:
                    matches = []
                    for bar in _extract_bars(raw):
                        stamp = timestamp(bar['t'])
                        if stamp and stamp <= closing and stamp.astimezone(ZoneInfo('America/New_York')).date() == day:
                            matches.append(bar)
                    if len(matches) == 1:
                        bar = matches[0]
                        if 0 < bar['l'] <= min(bar['o'], bar['c']) <= max(bar['o'], bar['c']) <= bar['h'] and bar['v'] >= 0:
                            result = dict(price=bar['c'], source='public-session-close', event_time=closing.isoformat(), fetched_at=datetime.now(UTC).isoformat())
            except Exception as exc:
                log.warning('Public completed close unavailable for %s: %s', symbol, type(exc).__name__)
            _CACHE[key] = (broker, time.monotonic(), result)
            _CACHE.move_to_end(key)
            while len(_CACHE) > 128:
                _CACHE.popitem(last=False)
            return dict(result) if result else None
    except Exception as exc:
        log.warning('Cannot verify Public completed session for %s: %s', symbol, type(exc).__name__)
        return None
