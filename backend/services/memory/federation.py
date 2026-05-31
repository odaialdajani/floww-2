#!/usr/bin/env python3
"""
backend/services/memory/federation.py — Federated mem0 sync service.

Uses a file-based federation queue (no external Redis dependency).
Each node publishes writes to a shared queue directory; subscribers
poll and apply with LWW (Last-Writer-Wins) conflict resolution.

For production with multiple machines, replace the file-based queue
with Upstash Redis pub-sub (channel: "mem0_writes").
"""

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path

try:
    import redis
except ImportError:
    redis = None  # type: ignore

logger = logging.getLogger(__name__)

# Federation queue directory (shared between local nodes)
FEDERATION_QUEUE_DIR = Path.home() / ".hermes" / "federation_queue"
FEDERATION_PROCESSED_DIR = FEDERATION_QUEUE_DIR / "processed"

# Node ID (unique per Hermes instance)
NODE_ID = os.environ.get("HERMES_NODE_ID", "node-local-1")

# Conflict resolution: LWW (Last-Writer-Wins)
LWW_GRACE_SECONDS = 5  # entries within 5s are considered concurrent


class FederationEvent:
    """A single federation event (write/delete)."""

    def __init__(self, node_id: str, entry_id: str, op: str, content: str,
                 timestamp_utc: float, tombstone: bool = False):
        self.node_id = node_id
        self.entry_id = entry_id
        self.op = op  # "write" or "delete"
        self.content = content
        self.timestamp_utc = timestamp_utc
        self.tombstone = tombstone

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "entry_id": self.entry_id,
            "op": self.op,
            "content": self.content,
            "timestamp_utc": self.timestamp_utc,
            "tombstone": self.tombstone,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FederationEvent":
        return cls(
            node_id=d["node_id"],
            entry_id=d["entry_id"],
            op=d["op"],
            content=d.get("content", ""),
            timestamp_utc=d["timestamp_utc"],
            tombstone=d.get("tombstone", False),
        )

    @property
    def event_id(self) -> str:
        raw = f"{self.node_id}:{self.entry_id}:{self.timestamp_utc}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class FileBasedFederationQueue:
    """File-based federation queue for single-machine multi-node simulation."""

    def __init__(self, queue_dir: Path = FEDERATION_QUEUE_DIR):
        self.queue_dir = queue_dir
        self.processed_dir = FEDERATION_PROCESSED_DIR
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def publish(self, event: FederationEvent):
        """Publish a write event to the federation queue."""
        event_path = self.queue_dir / f"{event.event_id}.json"
        event_path.write_text(json.dumps(event.to_dict()))
        logger.debug(f"Published event {event.event_id}: {event.op} {event.entry_id[:8]}")

    def poll(self, since_ts: float = 0, limit: int = 100) -> list[FederationEvent]:
        """Poll for new events since timestamp."""
        events = []
        for event_file in sorted(self.queue_dir.glob("*.json")):
            try:
                data = json.loads(event_file.read_text())
                if data["timestamp_utc"] > since_ts:
                    events.append(FederationEvent.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
            if len(events) >= limit:
                break
        return events

    def mark_processed(self, event: FederationEvent):
        """Mark an event as processed."""
        src = self.queue_dir / f"{event.event_id}.json"
        dst = self.processed_dir / f"{event.event_id}.json"
        if src.exists():
            src.rename(dst)


class FederatedMemorySync:
    """
    Federated memory sync service.

    On each mem0 write, publishes to the federation queue.
    Background thread polls for remote writes and applies them with LWW.
    """

    def __init__(self, mem0_client, user_id: str = "user_c778280e23af",
                 node_id: str = NODE_ID, use_redis: bool = False):
        self.client = mem0_client
        self.user_id = user_id
        self.node_id = node_id
        self.use_redis = use_redis

        if use_redis:
            self.queue = RedisFederationQueue()
        else:
            self.queue = FileBasedFederationQueue()

        self._last_poll_ts = time.time()
        self._running = False
        self._poll_thread = None

    def publish_write(self, entry_id: str, content: str):
        """Publish a write event after a local mem0 insert."""
        event = FederationEvent(
            node_id=self.node_id,
            entry_id=entry_id,
            op="write",
            content=content,
            timestamp_utc=time.time(),
        )
        self.queue.publish(event)

    def publish_delete(self, entry_id: str):
        """Publish a delete event."""
        event = FederationEvent(
            node_id=self.node_id,
            entry_id=entry_id,
            op="delete",
            content="",
            timestamp_utc=time.time(),
            tombstone=True,
        )
        self.queue.publish(event)

    def apply_remote_event(self, event: FederationEvent) -> bool:
        """
        Apply a remote federation event with LWW conflict resolution.

        Returns True if the event was applied, False if skipped (local wins).
        """
        if event.node_id == self.node_id:
            return False  # Skip own events

        try:
            if event.op == "delete" or event.tombstone:
                # Tombstone: mark as deleted (keep for 30d then GC)
                logger.info(f"Federation: tombstone {event.entry_id[:8]} from {event.node_id}")
                # In mem0, we can't truly delete via API, but we can tag
                try:
                    self.client.update(
                        memory_id=event.entry_id,
                        metadata={"tombstone": True, "federation_deleted": True}
                    )
                except Exception:
                    pass  # Entry may not exist locally
                return True

            elif event.op == "write":
                # LWW: check if local entry exists and is newer
                try:
                    local_results = self.client.search(
                        query=event.content[:50],
                        filters={"user_id": self.user_id},
                        limit=3,
                    )
                    for result in local_results:
                        if result.get("id") == event.entry_id:
                            local_ts = result.get("created_at", 0)
                            if isinstance(local_ts, str):
                                from dateutil.parser import parse as parse_dt
                                local_ts = parse_dt(local_ts).timestamp()
                            if local_ts > event.timestamp_utc:
                                logger.debug(f"LWW: local wins for {event.entry_id[:8]}")
                                return False
                except Exception:
                    pass

                # Apply remote write
                logger.info(f"Federation: applying write {event.entry_id[:8]} from {event.node_id}")
                self.client.add(
                    messages=[{"role": "user", "content": event.content}],
                    user_id=self.user_id,
                    metadata={"federation_source": event.node_id, "federation_synced": True},
                )
                return True

        except Exception as e:
            logger.error(f"Federation: failed to apply event {event.event_id}: {e}")
            return False

    def sync_once(self) -> int:
        """Poll and apply remote events. Returns number of events applied."""
        if self.use_redis:
            return self._sync_redis()
        return self._sync_file()

    def _sync_file(self) -> int:
        """File-based sync."""
        events = self.queue.poll(since_ts=self._last_poll_ts)
        applied = 0
        for event in events:
            if self.apply_remote_event(event):
                applied += 1
            if isinstance(self.queue, FileBasedFederationQueue):
                self.queue.mark_processed(event)
            self._last_poll_ts = max(self._last_poll_ts, event.timestamp_utc)
        return applied

    def _sync_redis(self) -> int:
        """Redis-based sync (subscribe mode)."""
        pubsub = self.queue.subscribe()
        applied = 0
        for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    event = FederationEvent.from_dict(data)
                    if self.apply_remote_event(event):
                        applied += 1
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Federation: bad message: {e}")
        return applied

    def start_background_sync(self, interval_seconds: int = 30):
        """Start background polling thread."""
        self._running = True

        def _poll_loop():
            while self._running:
                try:
                    count = self.sync_once()
                    if count > 0:
                        logger.info(f"Federation: synced {count} events")
                except Exception as e:
                    logger.error(f"Federation sync error: {e}")
                time.sleep(interval_seconds)

        self._poll_thread = threading.Thread(target=_poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info(f"Federation sync started (node: {self.node_id})")

    def stop(self):
        """Stop background sync."""
        self._running = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)

class RedisFederationQueue:
    """Redis-based federation queue for multi-machine setup."""

    def __init__(self, redis_url: str = None):
        if redis is None:
            raise ImportError("redis package required for RedisFederationQueue. pip install redis")
        self.redis_url = redis_url or os.environ.get(
            "REDIS_FEDERATION_URL", "redis://localhost:6379/0"
        )
        self.channel = "mem0_writes"
        self._redis = None

