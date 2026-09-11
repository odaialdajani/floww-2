"""Provider-neutral point-in-time event envelope (DATA-CONTRACT-1).

RED contract: no shared schema exists for normalized market-data rows.
Producers stamp ad-hoc timestamp fields (ts / fetched_at / now() fallback),
so event time and receive time are conflated and replay cannot reconstruct
what was known at a decision timestamp. normalize_event() carries source,
schema version, instrument identity, event/receive time, sequence,
correction state, entitlement/delay metadata, raw-vs-derived class, and
quality flags on every row. Synthetic fixtures only — no vendor rows, no
consumer cutover.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.event_envelope import is_point_in_time_complete, normalize_event  # noqa: E402


def _raw(**over):
    base = {
        "source": "synthetic-test",
        "symbol": "SPY",
        "event_time": "2026-09-09T14:30:00",
        "receive_time": "2026-09-09T14:30:01",
        "sequence": 42,
        "price": 500.0,
    }
    base.update(over)
    return base


class TestNormalizeEvent:
    def test_full_row_carries_provenance(self):
        env = normalize_event(_raw())
        assert env["source"] == "synthetic-test"
        assert env["schema_version"] == "1"
        assert env["symbol"] == "SPY"
        assert env["event_time"] == "2026-09-09T14:30:00"
        assert env["receive_time"] == "2026-09-09T14:30:01"
        assert env["sequence"] == 42
        assert env["correction"] == "unknown"
        assert env["delay_ms"] == 1000
        assert env["quality_flags"] == []
        assert env["raw_class"] == "raw"
        assert is_point_in_time_complete(env) is True

    def test_missing_event_time_is_flagged_not_fabricated(self):
        """No timestamp fallback to now(): unknown stays unknown."""
        env = normalize_event(_raw(event_time=None))
        assert env["event_time"] is None
        assert "missing_event_time" in env["quality_flags"]
        assert env["delay_ms"] is None
        assert is_point_in_time_complete(env) is False

    def test_missing_sequence_is_flagged(self):
        env = normalize_event(_raw(sequence=None))
        assert env["sequence"] is None
        assert "missing_sequence" in env["quality_flags"]

    def test_string_sequence_coerced(self):
        env = normalize_event(_raw(sequence="42"))
        assert env["sequence"] == 42

    def test_correction_state_mapping(self):
        assert normalize_event(_raw(is_correction=True))["correction"] == "correction"
        assert normalize_event(_raw(cancelled=True))["correction"] == "canceled"
        assert normalize_event(_raw(is_cancel=True))["correction"] == "canceled"

    def test_negative_delay_flagged(self):
        """Receive before event is impossible: flag, never a negative delay."""
        env = normalize_event(_raw(event_time="2026-09-09T14:30:02",
                                   receive_time="2026-09-09T14:30:01"))
        assert env["delay_ms"] is None
        assert "negative_delay" in env["quality_flags"]

    def test_derived_class_preserved(self):
        env = normalize_event(_raw(raw_class="derived", model="composite-1.2"))
        assert env["raw_class"] == "derived"
        assert env["model_version"] == "composite-1.2"

    def test_non_dict_and_empty_inputs_never_raise(self):
        env = normalize_event(None, source="s")
        assert env["event_time"] is None
        assert "missing_event_time" in env["quality_flags"]
        assert normalize_event({}, source="s")["symbol"] is None

    def test_alternate_timestamp_keys_accepted(self):
        env = normalize_event({"source": "s", "symbol": "QQQ",
                               "event_ts": "2026-09-09T14:30:00",
                               "fetched_at": "2026-09-09T14:30:05",
                               "seq": 7})
        assert env["event_time"] == "2026-09-09T14:30:00"
        assert env["receive_time"] == "2026-09-09T14:30:05"
        assert env["sequence"] == 7
        assert env["delay_ms"] == 5000
