import asyncio
import logging
from typing import Dict, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RequestDeduplicator:
    """Deduplicate concurrent identical API requests using asyncio.Future.

    When multiple coroutines call ``execute`` with the same key before the
    first underlying call finishes, they all share a single Future. When the
    underlying call completes, the result or exception is broadcast to every
    waiter.
    """

    def __init__(self) -> None:
        self._inflight: Dict[str, asyncio.Future] = {}

    async def execute(self, key: str, func) -> T:
        """Execute *func* once for *key*, deduping concurrent callers.

        Callers with the same outstanding key receive the result (or raise
        the same exception) without invoking *func* again.
        """
        loop = asyncio.get_running_loop()
        existing = self._inflight.get(key)
        if existing is not None:
            logger.debug("dedup: awaiting existing request %s", key)
            try:
                return await existing
            except Exception:
                # The shard may have been replaced by a *new* future since
                # we awaited the old one; fall through to a fresh attempt.
                pass

        future: asyncio.Future = loop.create_future()
        self._inflight[key] = future
        try:
            result = await func()
            future.set_result(result)
            return result
        except BaseException as exc:
            # Capture the exception so all waiters see it.
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            # Clean up so a later request can retry.
            self._inflight.pop(key, None)

    @property
    def inflight_keys(self):
        return list(self._inflight.keys())


deduplicator = RequestDeduplicator()
