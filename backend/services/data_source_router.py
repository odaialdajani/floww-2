"""
backend/services/data_source_router.py

Feature-flagged data source switching layer.
Reads ``FLOWW_DATA_SOURCE`` env var and routes data requests to the
correct provider (Alpha Vantage, Databento, Schwab, or auto-fallback).

Usage::

    from services.data_source_router import get_data_source, get_active_source_info

    source = get_data_source()  # Returns e.g. "alpha_vantage"
    info = get_active_source_info()  # Returns dict with delay, key status, etc.

Env:
    FLOWW_DATA_SOURCE ∈ {alpha_vantage, databento, schwab, auto}
    Default: auto (tries AV first if key present, then databento, then schwab)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── Source constants ──────────────────────────────────────────────────

ALPHA_VANTAGE = "alpha_vantage"
DATABENTO = "databento"
SCHWAB = "schwab"
AUTO = "auto"

VALID_SOURCES = {ALPHA_VANTAGE, DATABENTO, SCHWAB, AUTO}

# Known delays per source (seconds)
SOURCE_DELAYS: Dict[str, int] = {
    ALPHA_VANTAGE: 900,      # 15 min for AV free tier
    DATABENTO: 0,            # real-time (paid)
    SCHWAB: 0,               # real-time
}

# ── Active source tracking ────────────────────────────────────────────

_active_source: Optional[str] = None  # Resolved at first call
_last_resolved: Optional[str] = None  # Timestamp of last resolution

# Prometheus gauge label (lazy import to avoid startup dependency)
_prometheus_gauges_initialized = False


def _init_prometheus():
    """Initialize Prometheus metrics for data source tracking."""
    global _prometheus_gauges_initialized
    if _prometheus_gauges_initialized:
        return
    try:
        from services.observability import provider_calls_total
        # We use provider_calls_total for data source labels
        _prometheus_gauges_initialized = True
    except ImportError:
        pass


def get_configured_source() -> str:
    """Return the raw env var value (or 'auto' default)."""
    return os.environ.get("FLOWW_DATA_SOURCE", AUTO).strip().lower()


def _resolve_auto_source() -> str:
    """Resolve ``auto``: pick the first available source.

    Resolution order:
        1. Alpha Vantage (if key present)
        2. Databento (if key present)
        3. Schwab (always available, may be degraded)
    """
    av_key = os.environ.get("ALPHA_VANTAGE_KEY", "")
    if av_key:
        logger.info("DataSourceRouter: auto-resolved to alpha_vantage")
        return ALPHA_VANTAGE

    db_key = os.environ.get("DATABENTO_API_KEY", "")
    if db_key:
        logger.info("DataSourceRouter: auto-resolved to databento")
        return DATABENTO

    logger.info("DataSourceRouter: auto-resolved to schwab (fallback)")
    return SCHWAB


def get_data_source() -> str:
    """Return the active data source identifier.

    Resolves ``auto`` on first call (or after env change).
    Caches the resolved value until the env var changes.
    """
    global _active_source, _last_resolved

    configured = get_configured_source()

    if configured not in VALID_SOURCES:
        logger.warning(f"DataSourceRouter: invalid FLOWW_DATA_SOURCE={configured!r}, falling back to auto")
        configured = AUTO

    if configured != AUTO:
        _active_source = configured
    else:
        if _active_source is None:
            _active_source = _resolve_auto_source()
        _last_resolved = datetime.now(timezone.utc).isoformat()

    _init_prometheus()
    return _active_source


def get_active_source_info() -> Dict:
    """Return metadata about the active data source.

    Returns:
        dict with keys:
            - active (str): source name
            - delay_seconds (int): known data delay
            - configured (str): raw FLOWW_DATA_SOURCE env value
            - key_present (bool): whether the relevant API key is set
            - last_resolved (str|None): ISO timestamp of last auto-resolution
            - asof (str): current server time
    """
    source = get_data_source()
    return {
        "active": source,
        "delay_seconds": SOURCE_DELAYS.get(source, 0),
        "configured": get_configured_source(),
        "key_present": _check_key_present(source),
        "last_resolved": _last_resolved,
        "asof": datetime.now(timezone.utc).isoformat(),
    }


def _check_key_present(source: str) -> bool:
    """Check whether the API key for *source* is set."""
    key_map = {
        ALPHA_VANTAGE: "ALPHA_VANTAGE_KEY",
        DATABENTO: "DATABENTO_API_KEY",
        SCHWAB: "SCHWAB_APP_KEY",  # Schwab key may have a different name
    }
    env_key = key_map.get(source)
    if not env_key:
        return False
    return bool(os.environ.get(env_key, ""))


def set_data_source(source: str) -> bool:
    """Programmatically set the data source (overrides env).

    Useful for testing or runtime switching.
    Returns True if valid, False otherwise.
    """
    global _active_source
    if source not in VALID_SOURCES:
        logger.warning(f"DataSourceRouter: attempted to set invalid source {source!r}")
        return False
    _active_source = source if source != AUTO else _resolve_auto_source()
    logger.info(f"DataSourceRouter: source set to {_active_source}")
    return True


def reset():
    """Reset the cached source (forces re-resolution on next call)."""
    global _active_source, _last_resolved
    _active_source = None
    _last_resolved = None
    logger.info("DataSourceRouter: cache reset")
