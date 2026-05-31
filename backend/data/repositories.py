"""
Data layer for Confluence Decoder.

Provides repository pattern for MongoDB access with:
- Type-safe document schemas
- Proper indexing
- Data quality validation
- Migration support
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ─── Document Schemas ───

class GexSnapshot(BaseModel):
    """GEX snapshot document schema."""
    ticker: str
    ts: str  # ISO format timestamp
    spot: float
    total_gex: float = 0
    net_gex: float = 0
    king_strike: float = 0
    king_gex: float = 0
    top_floor: float = 0
    top_ceiling: float = 0
    regime: str = "unknown"  # POSITIVE, NEGATIVE, unknown
    strikes_compact: List[Dict[str, float]] = []

    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "SPY",
                "ts": "2025-01-01T00:00:00Z",
                "spot": 450.0,
                "total_gex": 1e9,
                "net_gex": 5e8,
                "king_strike": 450.0,
                "king_gex": 1e8,
                "top_floor": 455.0,
                "top_ceiling": 440.0,
                "regime": "POSITIVE",
                "strikes_compact": [{"strike": 450.0, "gex": 1e8}],
            }
        }


class AlertHistory(BaseModel):
    """Alert history document schema."""
    ticker: str
    ts: str
    alert_type: str
    priority: str  # HIGH, MEDIUM, LOW
    message: str
    snapshot_id: Optional[str] = None
    predicate_value: Optional[float] = None
    ml_prediction: Optional[Dict[str, Any]] = None
    realized_outcome: Optional[Dict[str, Any]] = None  # Filled later
    quality_score: Optional[float] = None  # From backtest

    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "SPY",
                "ts": "2025-01-01T00:00:00Z",
                "alert_type": "GAMMA_FLIP",
                "priority": "HIGH",
                "message": "Regime change detected",
            }
        }


class OrderRecord(BaseModel):
    """Order record document schema."""
    client_order_id: str
    ticker: str
    status: str  # pending, partial, filled, cancelled
    side: str  # buy, sell
    quantity: float
    order_type: str  # market, limit, stop
    limit_price: Optional[float] = None
    alpaca_order_id: Optional[str] = None
    filled_price: Optional[float] = None
    created_at: str = ""
    updated_at: str = ""


class PositionRecord(BaseModel):
    """Position record document schema."""
    ticker: str
    status: str  # open, closed
    quantity: float
    entry_price: float
    entry_ts: str = ""
    exit_price: Optional[float] = None
    exit_ts: Optional[str] = None
    events: List[Dict[str, Any]] = []


class GexSnapshotRepository:
    """Repository for GEX snapshots."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.snapshots

    async def create_indexes(self):
        """Create required indexes."""
        await self.collection.create_index([("ticker", 1), ("ts", -1)])
        await self.collection.create_index([("regime", 1)])
        await self.collection.create_index([("ts", -1)])

    async def insert(self, snapshot: GexSnapshot) -> str:
        """Insert a snapshot."""
        doc = snapshot.model_dump()
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def find_latest(self, ticker: str) -> Optional[GexSnapshot]:
        """Find the latest snapshot for a ticker."""
        doc = await self.collection.find_one(
            {"ticker": ticker},
            sort=[("ts", -1)]
        )
        return GexSnapshot(**doc) if doc else None

    async def find_previous(self, ticker: str, before_ts: str) -> Optional[GexSnapshot]:
        """Find the snapshot before a given timestamp."""
        doc = await self.collection.find_one(
            {"ticker": ticker, "ts": {"$lt": before_ts}},
            sort=[("ts", -1)]
        )
        return GexSnapshot(**doc) if doc else None

    async def find_range(
        self,
        ticker: str,
        start_ts: str,
        end_ts: str,
        limit: int = 1000,
    ) -> List[GexSnapshot]:
        """Find snapshots in a time range."""
        cursor = self.collection.find(
            {"ticker": ticker, "ts": {"$gte": start_ts, "$lte": end_ts}},
            sort=[("ts", 1)],
        ).limit(limit)

        return [GexSnapshot(**doc) async for doc in cursor]

    async def count(self, ticker: str) -> int:
        """Count snapshots for a ticker."""
        return await self.collection.count_documents({"ticker": ticker})


class AlertHistoryRepository:
    """Repository for alert history."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.alerts_history

    async def create_indexes(self):
        """Create required indexes."""
        await self.collection.create_index([("ticker", 1), ("ts", -1)])
        await self.collection.create_index([("alert_type", 1)])
        await self.collection.create_index([("priority", 1)])

    async def insert(self, alert: AlertHistory) -> str:
        """Insert an alert record."""
        doc = alert.model_dump()
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def find_by_ticker(
        self,
        ticker: str,
        limit: int = 100,
    ) -> List[AlertHistory]:
        """Find alerts for a ticker."""
        cursor = self.collection.find(
            {"ticker": ticker},
            sort=[("ts", -1)],
        ).limit(limit)

        return [AlertHistory(**doc) async for doc in cursor]

    async def update_outcome(
        self,
        alert_id: str,
        outcome: Dict[str, Any],
    ):
        """Update the realized outcome of an alert."""
        await self.collection.update_one(
            {"_id": alert_id},
            {"$set": {"realized_outcome": outcome}},
        )


class OrderRepository:
    """Repository for order records."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.orders

    async def create_indexes(self):
        """Create required indexes."""
        await self.collection.create_index([("client_order_id", 1)], unique=True)
        await self.collection.create_index([("ticker", 1), ("status", 1)])
        await self.collection.create_index([("created_at", -1)])

    async def insert(self, order: OrderRecord) -> str:
        """Insert an order record."""
        doc = order.model_dump()
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def find_by_client_id(self, client_order_id: str) -> Optional[OrderRecord]:
        """Find order by client order ID."""
        doc = await self.collection.find_one({"client_order_id": client_order_id})
        return OrderRecord(**doc) if doc else None

    async def update_status(
        self,
        client_order_id: str,
        status: str,
        alpaca_order_id: Optional[str] = None,
        filled_price: Optional[float] = None,
    ):
        """Update order status."""
        update = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if alpaca_order_id:
            update["alpaca_order_id"] = alpaca_order_id
        if filled_price is not None:
            update["filled_price"] = filled_price

        await self.collection.update_one(
            {"client_order_id": client_order_id},
            {"$set": update},
        )

    async def find_open_orders(self, ticker: Optional[str] = None) -> List[OrderRecord]:
        """Find open orders."""
        query = {"status": {"$in": ["pending", "partial"]}}
        if ticker:
            query["ticker"] = ticker

        cursor = self.collection.find(query, sort=[("created_at", -1)])
        return [OrderRecord(**doc) async for doc in cursor]


class PositionRepository:
    """Repository for position records."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.positions

    async def create_indexes(self):
        """Create required indexes."""
        await self.collection.create_index([("ticker", 1), ("status", 1)])
        await self.collection.create_index([("entry_ts", -1)])

    async def insert(self, position: PositionRecord) -> str:
        """Insert a position record."""
        doc = position.model_dump()
        result = await self.collection.insert_one(doc)
        return str(result.inserted_id)

    async def find_open_positions(self, ticker: Optional[str] = None) -> List[PositionRecord]:
        """Find open positions."""
        query = {"status": "open"}
        if ticker:
            query["ticker"] = ticker

        cursor = self.collection.find(query, sort=[("entry_ts", -1)])
        return [PositionRecord(**doc) async for doc in cursor]

    async def add_event(self, position_id: str, event: Dict[str, Any]):
        """Add an event to a position's event log."""
        await self.collection.update_one(
            {"_id": position_id},
            {"$push": {"events": event}},
        )

    async def close_position(
        self,
        position_id: str,
        exit_price: float,
        pnl: float,
    ):
        """Close a position."""
        await self.collection.update_one(
            {"_id": position_id},
            {"$set": {
                "status": "closed",
                "exit_price": exit_price,
                "exit_ts": datetime.now(timezone.utc).isoformat(),
                "pnl": pnl,
            }},
        )


# ─── Data Quality ───

class DataQualityChecker:
    """Validates data quality for incoming snapshots."""

    @staticmethod
    def validate_snapshot(snapshot: GexSnapshot) -> List[str]:
        """Validate a snapshot. Returns list of issues (empty = valid)."""
        issues = []

        if snapshot.spot <= 0:
            issues.append(f"Invalid spot price: {snapshot.spot}")

        if not snapshot.ticker:
            issues.append("Missing ticker")

        if snapshot.regime not in ("POSITIVE", "NEGATIVE", "unknown"):
            issues.append(f"Invalid regime: {snapshot.regime}")

        if snapshot.total_gex == 0 and snapshot.net_gex == 0:
            issues.append("Zero GEX values — possible data issue")

        if not snapshot.strikes_compact:
            issues.append("No strike data")

        return issues

    @staticmethod
    def validate_alert(alert: AlertHistory) -> List[str]:
        """Validate an alert record."""
        issues = []

        if alert.priority not in ("HIGH", "MEDIUM", "LOW"):
            issues.append(f"Invalid priority: {alert.priority}")

        if not alert.alert_type:
            issues.append("Missing alert type")

        return issues
