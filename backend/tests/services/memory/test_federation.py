#!/usr/bin/env python3
"""
backend/tests/services/memory/test_federation.py — Tests for federated mem0 sync.

Run: pytest backend/tests/services/memory/test_federation.py -v
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.memory.federation import (
    FederatedMemorySync,
    FederationEvent,
    FileBasedFederationQueue,
)


@pytest.fixture
def tmp_queue_dir(tmp_path):
    """Create a temporary federation queue directory."""
    qdir = tmp_path / "federation_queue"
    qdir.mkdir()
    return qdir


@pytest.fixture
def mock_mem0_client():
    """Create a mock mem0 client."""
    client = MagicMock()
    client.get_all.return_value = []
    client.search.return_value = []
    client.add.return_value = {"id": "test-entry-1"}
    client.update.return_value = True
    return client


class TestFederationEvent:
    def test_create_event(self):
        event = FederationEvent(
            node_id="node-a",
            entry_id="entry-1",
            op="write",
            content="test content",
            timestamp_utc=1000.0,
        )
        assert event.node_id == "node-a"
        assert event.op == "write"
        assert event.tombstone is False

    def test_serialization(self):
        event = FederationEvent(
            node_id="node-a",
            entry_id="entry-1",
            op="write",
            content="test content",
            timestamp_utc=1000.0,
        )
        d = event.to_dict()
        restored = FederationEvent.from_dict(d)
        assert restored.node_id == event.node_id
        assert restored.entry_id == event.entry_id
        assert restored.op == event.op
        assert restored.content == event.content

    def test_tombstone_event(self):
        event = FederationEvent(
            node_id="node-a",
            entry_id="entry-1",
            op="delete",
            content="",
            timestamp_utc=1000.0,
            tombstone=True,
        )
        assert event.tombstone is True
        d = event.to_dict()
        assert d["tombstone"] is True

    def test_event_id_deterministic(self):
        event = FederationEvent(
            node_id="node-a",
            entry_id="entry-1",
            op="write",
            content="test",
            timestamp_utc=1000.0,
        )
        assert event.event_id == event.event_id  # Deterministic


class TestFileBasedFederationQueue:
    def test_publish_and_poll(self, tmp_queue_dir):
        queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)
        event = FederationEvent(
            node_id="node-a",
            entry_id="entry-1",
            op="write",
            content="test content",
            timestamp_utc=time.time(),
        )
        queue.publish(event)
        events = queue.poll()
        assert len(events) == 1
        assert events[0].entry_id == "entry-1"

    def test_poll_since_timestamp(self, tmp_queue_dir):
        queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)
        old_event = FederationEvent(
            node_id="node-a",
            entry_id="old",
            op="write",
            content="old",
            timestamp_utc=1000.0,
        )
        new_event = FederationEvent(
            node_id="node-a",
            entry_id="new",
            op="write",
            content="new",
            timestamp_utc=2000.0,
        )
        queue.publish(old_event)
        queue.publish(new_event)

        events = queue.poll(since_ts=1500.0)
        assert len(events) == 1
        assert events[0].entry_id == "new"

    def test_mark_processed(self, tmp_queue_dir):
        queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)
        event = FederationEvent(
            node_id="node-a",
            entry_id="entry-1",
            op="write",
            content="test",
            timestamp_utc=time.time(),
        )
        queue.publish(event)
        queue.mark_processed(event)

        # Should not appear in poll after processing
        remaining = [e for e in queue.poll() if e.event_id == event.event_id]
        assert len(remaining) == 0

    def test_multiple_events_ordered(self, tmp_queue_dir):
        queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)
        for i in range(5):
            event = FederationEvent(
                node_id="node-a",
                entry_id=f"entry-{i}",
                op="write",
                content=f"content-{i}",
                timestamp_utc=1000.0 + i,
            )
            queue.publish(event)

        events = queue.poll()
        assert len(events) == 5


class TestFederatedMemorySync:
    def test_publish_write(self, tmp_queue_dir, mock_mem0_client):
        sync = FederatedMemorySync(
            mem0_client=mock_mem0_client,
            use_redis=False,
        )
        sync.queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)

        sync.publish_write("entry-1", "test content")

        events = sync.queue.poll()
        assert len(events) == 1
        assert events[0].op == "write"
        assert events[0].content == "test content"

    def test_publish_delete(self, tmp_queue_dir, mock_mem0_client):
        sync = FederatedMemorySync(
            mem0_client=mock_mem0_client,
            use_redis=False,
        )
        sync.queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)

        sync.publish_delete("entry-1")

        events = sync.queue.poll()
        assert len(events) == 1
        assert events[0].tombstone is True

    def test_skip_own_events(self, tmp_queue_dir, mock_mem0_client):
        sync = FederatedMemorySync(
            mem0_client=mock_mem0_client,
            node_id="node-a",
            use_redis=False,
        )
        sync.queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)

        # Create event from same node
        event = FederationEvent(
            node_id="node-a",
            entry_id="entry-1",
            op="write",
            content="test",
            timestamp_utc=time.time(),
        )
        sync.queue.publish(event)

        applied = sync.sync_once()
        assert applied == 0  # Should skip own events

    def test_apply_remote_write(self, tmp_queue_dir, mock_mem0_client):
        sync = FederatedMemorySync(
            mem0_client=mock_mem0_client,
            node_id="node-a",
            use_redis=False,
        )
        sync.queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)

        # Create event from different node
        event = FederationEvent(
            node_id="node-b",
            entry_id="entry-remote",
            op="write",
            content="remote content",
            timestamp_utc=time.time(),
        )
        sync.queue.publish(event)

        applied = sync.sync_once()
        assert applied == 1
        mock_mem0_client.add.assert_called_once()

    def test_lww_local_wins(self, tmp_queue_dir, mock_mem0_client):
        """When local entry is newer, remote write should be skipped."""
        sync = FederatedMemorySync(
            mem0_client=mock_mem0_client,
            node_id="node-a",
            use_redis=False,
        )
        sync.queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)

        # Mock: local search returns a newer entry
        mock_mem0_client.search.return_value = [{
            "id": "entry-1",
            "created_at": "2026-05-20T00:02:00Z",  # Newer
        }]

        event = FederationEvent(
            node_id="node-b",
            entry_id="entry-1",
            op="write",
            content="remote content",
            timestamp_utc=1000.0,  # Older
        )
        sync.queue.publish(event)

        applied = sync.sync_once()
        assert applied == 0  # Local wins, remote skipped

    def test_2_node_convergence(self, tmp_queue_dir, mock_mem0_client):
        """Simulate 2-node sync: A writes, B receives."""
        sync_a = FederatedMemorySync(
            mem0_client=mock_mem0_client,
            node_id="node-a",
            use_redis=False,
        )
        sync_a.queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)

        sync_b = FederatedMemorySync(
            mem0_client=mock_mem0_client,
            node_id="node-b",
            use_redis=False,
        )
        sync_b.queue = FileBasedFederationQueue(queue_dir=tmp_queue_dir)

        # Node A publishes a write
        sync_a.publish_write("entry-1", "content from A")

        # Node B syncs and receives
        applied = sync_b.sync_once()
        assert applied == 1

        # Node B publishes a different write
        sync_b.publish_write("entry-2", "content from B")

        # Node A syncs and receives
        applied = sync_a.sync_once()
        assert applied == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
