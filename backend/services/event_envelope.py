"""Provider-neutral point-in-time event envelope.

Every normalized row carries source, schema version, instrument identity,
event time, receive time, sequence if available, correction/cancel state,
entitlement mode, delay, raw/derived class, and quality flags so training
and evaluation data is reconstructable as known at the decision timestamp.

Unknown stays unknown: nothing here fabricates a timestamp, a sequence, or
a correction state. Synthetic fixtures only — no vendor payloads.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

SCHEMA_VERSION = "1"


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_seq(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _correction_state(raw: dict[str, Any]) -> str:
    if raw.get("is_correction") is True:
        return "correction"
    if raw.get("cancelled") is True or raw.get("is_cancel") is True:
        return "canceled"
    state = raw.get("correction")
    if isinstance(state, str) and state.strip():
        return state.strip().lower()
    return "unknown"


def normalize_event(raw: Any, *, source: str | None = None,
                    schema_version: str = SCHEMA_VERSION,
                    received_at: str | None = None) -> dict[str, Any]:
    """Normalize one raw row into a point-in-time envelope.

    Never raises on malformed input: problems surface as quality flags.
    """
    if not isinstance(raw, dict):
        raw = {}
    flags: list[str] = []

    event_dt = (_parse_dt(raw.get("event_time"))
                or _parse_dt(raw.get("event_ts"))
                or _parse_dt(raw.get("ts")))
    if event_dt is None:
        flags.append("missing_event_time")

    receive_dt = (_parse_dt(raw.get("receive_time"))
                  or _parse_dt(raw.get("received_at"))
                  or _parse_dt(raw.get("fetched_at"))
                  or _parse_dt(received_at))

    sequence = (_parse_seq(raw.get("sequence"))
                if raw.get("sequence") is not None
                else _parse_seq(raw.get("seq")))
    if sequence is None:
        flags.append("missing_sequence")

    delay_ms: int | None = None
    if event_dt is not None and receive_dt is not None:
        delta = (receive_dt - event_dt).total_seconds() * 1000
        if delta < 0:
            flags.append("negative_delay")
        else:
            delay_ms = int(delta)

    raw_class = raw.get("raw_class", "raw")
    if raw_class not in ("raw", "derived"):
        raw_class = "raw"

    claimed_source = source if source is not None else raw.get("source")
    if not isinstance(claimed_source, str) or not claimed_source.strip():
        claimed_source = "unknown"

    return {
        "source": claimed_source,
        "schema_version": schema_version,
        "symbol": raw.get("symbol"),
        "event_time": event_dt.isoformat() if event_dt else None,
        "receive_time": receive_dt.isoformat() if receive_dt else None,
        "sequence": sequence,
        "correction": _correction_state(raw),
        "entitlement": raw.get("entitlement", "unknown"),
        "delay_ms": delay_ms,
        "raw_class": raw_class,
        "model_version": raw.get("model_version", raw.get("model")),
        "quality_flags": flags,
        "payload": {k: v for k, v in raw.items()},
    }


def is_point_in_time_complete(envelope: dict[str, Any]) -> bool:
    """True when the row can anchor a point-in-time join."""
    return (envelope.get("event_time") is not None
            and "missing_event_time" not in envelope.get("quality_flags", []))
