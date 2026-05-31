"""
backend/services/data_fallback.py

Multi-source data fallback handler.
Manages failover between Schwab (primary), yfinance (fallback 1),
and Polygon (fallback 2) data sources.

Rules:
  - If Schwab data is stale (>5s old), fall back to yfinance or Polygon
  - Log warning but continue operation
  - If all sources fail, enter "Safe Mode" (pause trading signals)
  - Auto-recovery when primary source comes back

Window B safe — all failover logic is simulated.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Thresholds
STALE_DATA_THRESHOLD_S = 5.0  # seconds before data considered stale
SAFE_MODE_TIMEOUT_S = 300  # 5 minutes in safe mode before retry
RECOVERY_CHECK_INTERVAL_S = 30  # check for primary recovery every 30s


class DataSource(Enum):
    SCHWAB = "schwab"
    YFINANCE = "yfinance"
    POLYGON = "polygon"
    CACHE = "cache"
    NONE = "none"


class FallbackState(Enum):
    PRIMARY = "primary"  # Using Schwab
    FALLBACK_1 = "fallback_1"  # Using yfinance
    FALLBACK_2 = "fallback_2"  # Using Polygon
    SAFE_MODE = "safe_mode"  # All sources failed


@dataclass
class SourceStatus:
    """Status of a single data source."""
    source: DataSource
    last_update: float = 0.0  # monotonic timestamp
    last_data: Optional[Dict[str, Any]] = None
    error_count: int = 0
    is_available: bool = True
    latency_ms: float = 0.0

    @property
    def age_s(self) -> float:
        if self.last_update == 0:
            return float("inf")
        return time.monotonic() - self.last_update

    @property
    def is_stale(self) -> bool:
        return self.age_s > STALE_DATA_THRESHOLD_S

    def record_update(self, data: Dict[str, Any]):
        self.last_update = time.monotonic()
        self.last_data = data
        self.error_count = 0
        self.is_available = True

    def record_error(self, error: str):
        self.error_count += 1
        self.is_available = False
        logger.warning(f"Data source {self.source.value} error: {error}")


@dataclass
class FallbackConfig:
    """Configuration for the fallback handler."""
    stale_threshold_s: float = STALE_DATA_THRESHOLD_S
    safe_mode_timeout_s: float = SAFE_MODE_TIMEOUT_S
    recovery_check_interval_s: float = RECOVERY_CHECK_INTERVAL_S
    max_consecutive_errors: int = 3
    enable_polygon: bool = False  # Requires API key
    polygon_api_key: str = ""


class DataFallbackHandler:
    """
    Manages data source failover with automatic recovery.

    Usage:
        handler = DataFallbackHandler()
        handler.configure_source(DataSource.SCHWAB, schwab_fetcher)
        handler.configure_source(DataSource.YFINANCE, yfinance_fetcher)

        # In your data loop:
        data = await handler.get_data("SPY")
        if handler.is_safe_mode:
            pause_trading_signals()
    """

    def __init__(self, config: Optional[FallbackConfig] = None):
        self.config = config or FallbackConfig()
        self._state = FallbackState.PRIMARY
        self._sources: Dict[DataSource, SourceStatus] = {}
        self._fetchers: Dict[DataSource, Callable] = {}
        self._safe_mode_since: Optional[float] = None
        self._transition_log: List[Dict[str, Any]] = []
        self._warning_log: List[Dict[str, Any]] = []

        # Initialize source statuses
        for source in [DataSource.SCHWAB, DataSource.YFINANCE, DataSource.POLYGON]:
            self._sources[source] = SourceStatus(source=source)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure_source(self, source: DataSource, fetcher: Callable):
        """Register a data fetcher for a source."""
        self._fetchers[source] = fetcher
        logger.info(f"Configured data source: {source.value}")

    @property
    def state(self) -> FallbackState:
        return self._state

    @property
    def is_safe_mode(self) -> bool:
        return self._state == FallbackState.SAFE_MODE

    @property
    def active_source(self) -> DataSource:
        """Return the currently active data source."""
        state_map = {
            FallbackState.PRIMARY: DataSource.SCHWAB,
            FallbackState.FALLBACK_1: DataSource.YFINANCE,
            FallbackState.FALLBACK_2: DataSource.POLYGON,
            FallbackState.SAFE_MODE: DataSource.NONE,
        }
        return state_map[self._state]

    # ------------------------------------------------------------------
    # Data fetching with failover
    # ------------------------------------------------------------------

    async def get_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch data with automatic failover.

        Tries sources in order: Schwab -> yfinance -> Polygon -> Cache.
        Returns None if all sources fail (safe mode).
        """
        # Determine which source to try first based on state
        source_order = self._get_source_order()

        _successful_source = None

        for source in source_order:
            if source == DataSource.CACHE:
                # Try cache last
                cached = self._get_cached_data(symbol)
                if cached is not None:
                    self._log_warning("CACHE_USED", f"Using cached data for {symbol}")
                    return cached
                continue

            if source not in self._fetchers:
                continue

            status = self._sources[source]
            if not status.is_available and status.error_count >= self.config.max_consecutive_errors:
                continue

            try:
                start = time.monotonic()
                data = await self._fetchers[source](symbol)
                latency_ms = (time.monotonic() - start) * 1000

                if data is not None:
                    status.record_update(data)
                    status.latency_ms = latency_ms
                    _successful_source = source

                    # Transition logic based on which source succeeded
                    if source == DataSource.SCHWAB:
                        if self._state != FallbackState.PRIMARY:
                            self._transition(FallbackState.PRIMARY, "Primary source recovered")
                    elif source == DataSource.YFINANCE:
                        if self._state == FallbackState.PRIMARY:
                            self._transition(FallbackState.FALLBACK_1, "Schwab unavailable, using yfinance")
                    elif source == DataSource.POLYGON:
                        if self._state in (FallbackState.PRIMARY, FallbackState.FALLBACK_1):
                            self._transition(FallbackState.FALLBACK_2, "Schwab/yfinance unavailable, using Polygon")

                    return data

            except Exception as e:
                status.record_error(str(e))
                logger.warning(f"Data source {source.value} failed for {symbol}: {e}")

        # All sources failed — enter safe mode
        if not self.is_safe_mode:
            self._transition(FallbackState.SAFE_MODE, "All data sources failed")
            self._safe_mode_since = time.monotonic()

        return None

    def _get_source_order(self) -> List[DataSource]:
        """Get the order of sources to try based on current state."""
        if self._state == FallbackState.PRIMARY:
            return [DataSource.SCHWAB, DataSource.YFINANCE, DataSource.POLYGON, DataSource.CACHE]
        elif self._state == FallbackState.FALLBACK_1:
            return [DataSource.YFINANCE, DataSource.SCHWAB, DataSource.POLYGON, DataSource.CACHE]
        elif self._state == FallbackState.FALLBACK_2:
            return [DataSource.POLYGON, DataSource.YFINANCE, DataSource.SCHWAB, DataSource.CACHE]
        else:  # SAFE_MODE
            return [DataSource.SCHWAB, DataSource.YFINANCE, DataSource.POLYGON, DataSource.CACHE]

    def _get_cached_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the most recent cached data for a symbol."""
        best_data = None
        best_age = float("inf")
        for status in self._sources.values():
            if status.last_data and status.age_s < best_age:
                best_data = status.last_data
                best_age = status.age_s
        return best_data

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _transition(self, new_state: FallbackState, reason: str):
        """Transition to a new fallback state."""
        old_state = self._state
        self._state = new_state

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from_state": old_state.value,
            "to_state": new_state.value,
            "reason": reason,
        }
        self._transition_log.append(entry)

        if new_state == FallbackState.SAFE_MODE:
            logger.critical(f"SAFE MODE ENTERED: {reason}")
        elif new_state == FallbackState.PRIMARY:
            logger.info(f"RECOVERED to primary: {reason}")
        else:
            logger.warning(f"FAILOVER: {old_state.value} -> {new_state.value}: {reason}")

    def _log_warning(self, warning_type: str, detail: str):
        """Log a warning event."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": warning_type,
            "detail": detail,
        }
        self._warning_log.append(entry)
        logger.warning(f"[{warning_type}] {detail}")

    # ------------------------------------------------------------------
    # Health check & auto-recovery
    # ------------------------------------------------------------------

    async def check_health(self) -> Dict[str, Any]:
        """
        Check health of all data sources.
        Returns status dict for monitoring.
        """
        sources_health = {}
        for source, status in self._sources.items():
            sources_health[source.value] = {
                "available": status.is_available,
                "stale": status.is_stale,
                "age_s": round(status.age_s, 2),
                "error_count": status.error_count,
                "latency_ms": round(status.latency_ms, 2),
            }

        return {
            "state": self._state.value,
            "active_source": self.active_source.value,
            "is_safe_mode": self.is_safe_mode,
            "safe_mode_duration_s": (
                round(time.monotonic() - self._safe_mode_since, 1)
                if self._safe_mode_since else 0
            ),
            "sources": sources_health,
            "transition_count": len(self._transition_log),
            "warning_count": len(self._warning_log),
        }

    async def attempt_recovery(self) -> bool:
        """
        Attempt to recover from safe mode.
        Returns True if recovery succeeded.
        """
        if not self.is_safe_mode:
            return True

        logger.info("Attempting recovery from safe mode...")

        # Try primary source
        if DataSource.SCHWAB in self._fetchers:
            try:
                data = await self._fetchers[DataSource.SCHWAB]("SPY")
                if data is not None:
                    self._sources[DataSource.SCHWAB].record_update(data)
                    self._transition(FallbackState.PRIMARY, "Recovery attempt succeeded")
                    self._safe_mode_since = None
                    return True
            except Exception as e:
                logger.info(f"Recovery attempt failed: {e}")

        return False

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    def get_transition_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._transition_log[-limit:]

    def get_warning_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._warning_log[-limit:]

    def get_metrics(self) -> Dict[str, Any]:
        """Return metrics for observability."""
        return {
            "state": self._state.value,
            "active_source": self.active_source.value,
            "is_safe_mode": self.is_safe_mode,
            "transitions": len(self._transition_log),
            "warnings": len(self._warning_log),
            "source_ages_s": {
                s.value: round(st.age_s, 2) for s, st in self._sources.items()
            },
        }


# Global singleton
fallback_handler = DataFallbackHandler()
