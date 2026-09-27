"""
backend/services/node_lifecycle.py

Node Lifecycle Tracker: State machine tracking spot price interactions
with King Nodes (local GEX maxima).

States:
  FORMED: Node has been identified as a King Node
  ACTIVE: Spot price is near the node (within threshold)
  TAPPED: Spot price has touched the node
  DECAYING: Node has been tapped multiple times, losing structural weight
  EXPIRED: Node is no longer relevant (too many taps or spot moved away)

Each tap reduces the node's visual opacity and structural weight,
modeling the idea that repeated tests of a gamma level weaken it.
"""
from __future__ import annotations

import math
from collections import deque
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class NodeState(Enum):
    FORMED = "formed"
    ACTIVE = "active"
    TAPPED = "tapped"
    DECAYING = "decaying"
    EXPIRED = "expired"


def _parse_dt(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


class Node:
    """Represents a single King Node in the lifecycle."""

    def __init__(self, strike: float, gex_value: float, spot_at_formation: float,
                 tap_threshold_pct: float = 0.003, max_taps: int = 5):
        self.strike = strike
        self.gex_value = gex_value
        self.spot_at_formation = spot_at_formation
        self.tap_threshold_pct = tap_threshold_pct
        self.max_taps = max_taps

        self.state = NodeState.FORMED
        self.tap_count = 0
        self.formation_time = datetime.now(UTC)
        self.last_tap_time: datetime | None = None
        self.tap_times: list[datetime] = []
        self.structural_weight = 1.0  # 1.0 = full strength, decays with taps
        self.opacity = 1.0  # visual opacity, decays with taps

    def check_tap(self, spot: float) -> bool:
        """Check if spot is within tap threshold of this node's strike."""
        threshold = self.strike * self.tap_threshold_pct
        return abs(spot - self.strike) <= threshold

    def tap(self) -> None:
        """Record a tap on this node."""
        now = datetime.now(UTC)
        self.tap_count += 1
        self.last_tap_time = now
        self.tap_times.append(now)

        # Decay structural weight: exponential decay
        self.structural_weight = math.exp(-0.3 * self.tap_count)
        # Decay opacity: linear decay
        self.opacity = max(0.1, 1.0 - (self.tap_count / self.max_taps) * 0.9)

        # State transitions
        if self.tap_count >= self.max_taps:
            self.state = NodeState.EXPIRED
        elif self.tap_count >= 3:
            self.state = NodeState.DECAYING
        else:
            self.state = NodeState.TAPPED

    def update(self, spot: float) -> None:
        """Update node state based on current spot price."""
        if self.state == NodeState.EXPIRED:
            return

        if self.check_tap(spot):
            self.tap()
        elif self.state in (NodeState.FORMED, NodeState.TAPPED, NodeState.DECAYING):
            # Check if spot is near but not tapping (active zone)
            extended_threshold = self.strike * self.tap_threshold_pct * 3
            if abs(spot - self.strike) <= extended_threshold:
                self.state = NodeState.ACTIVE

    @property
    def tap_probability_basis(self) -> str:
        return "heuristic"

    @property
    def tap_probability(self) -> float:
        """Deterministic tap-probability heuristic band.

        HEURISTIC (not a calibrated model): fresh nodes hold most often,
        repeated taps weaken the level. Bands mirror the desk convention
        (Fresh .80 / Tested-once .66 / Tested-twice .50 / Decaying .33 /
        Expired .10). Always surfaced with tap_probability_basis so no
        consumer mistakes it for a measured probability.
        """
        if self.state == NodeState.EXPIRED:
            return 0.10
        if self.state == NodeState.DECAYING or self.tap_count >= 3:
            return 0.33
        if self.tap_count == 2:
            return 0.50
        if self.tap_count == 1:
            return 0.66
        return 0.80

    def to_dict(self) -> dict[str, Any]:
        return {
            "strike": self.strike,
            "gex_value": round(self.gex_value, 2),
            "spot_at_formation": self.spot_at_formation,
            "tap_threshold_pct": self.tap_threshold_pct,
            "max_taps": self.max_taps,
            "state": self.state.value,
            "tap_count": self.tap_count,
            "structural_weight": round(self.structural_weight, 4),
            "opacity": round(self.opacity, 4),
            "formation_time": self.formation_time.isoformat(),
            "last_tap_time": self.last_tap_time.isoformat() if self.last_tap_time else None,
            "tap_times": [t.isoformat() for t in self.tap_times],
            "tap_probability": self.tap_probability,
            "tap_probability_basis": self.tap_probability_basis,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Node:
        """Rehydrate a Node from to_dict output (persistence round-trip)."""
        node = cls(
            strike=float(d["strike"]),
            gex_value=float(d.get("gex_value", 0.0)),
            spot_at_formation=float(d.get("spot_at_formation", d["strike"])),
            tap_threshold_pct=float(d.get("tap_threshold_pct", 0.003)),
            max_taps=int(d.get("max_taps", 5)),
        )
        node.state = NodeState(str(d.get("state", "formed")))
        node.tap_count = int(d.get("tap_count", 0))
        node.structural_weight = float(d.get("structural_weight", 1.0))
        node.opacity = float(d.get("opacity", 1.0))
        node.formation_time = _parse_dt(d.get("formation_time")) or datetime.now(UTC)
        node.last_tap_time = _parse_dt(d.get("last_tap_time"))
        node.tap_times = [t for t in (_parse_dt(x) for x in d.get("tap_times", [])) if t]
        return node


class NodeLifecycleTracker:
    """Tracks the lifecycle of all King Nodes across time."""

    def __init__(self, tap_threshold_pct: float = 0.003, max_taps: int = 5,
                 max_nodes: int = 20):
        self.tap_threshold_pct = tap_threshold_pct
        self.max_taps = max_taps
        self.max_nodes = max_nodes
        self._nodes: dict[float, Node] = {}  # strike -> Node
        self._history: deque[dict[str, Any]] = deque(maxlen=1000)

    def update(self, spot: float, king_nodes: list[tuple[float, float]]) -> dict[str, Any]:
        """Update all nodes with current spot and detected king nodes.

        Args:
            spot: current spot price
            king_nodes: list of (strike, gex_value) tuples

        Returns dict with active nodes, new taps, expired nodes, summary.
        """

        # Create new nodes for newly detected king nodes
        for strike, gex_value in king_nodes:
            if strike not in self._nodes:
                self._nodes[strike] = Node(
                    strike=strike,
                    gex_value=gex_value,
                    spot_at_formation=spot,
                    tap_threshold_pct=self.tap_threshold_pct,
                    max_taps=self.max_taps,
                )

        # Update all existing nodes
        new_taps = []
        expired = []
        for strike, node in list(self._nodes.items()):
            prev_state = node.state
            node.update(spot)
            if node.state == NodeState.TAPPED and prev_state != NodeState.TAPPED:
                new_taps.append(strike)
            if node.state == NodeState.EXPIRED:
                expired.append(strike)

        # Clean up expired nodes
        for strike in expired:
            del self._nodes[strike]

        # Limit total nodes
        if len(self._nodes) > self.max_nodes:
            # Remove oldest formed nodes
            sorted_nodes = sorted(self._nodes.items(), key=lambda x: x[1].formation_time)
            for strike, _ in sorted_nodes[:len(self._nodes) - self.max_nodes]:
                del self._nodes[strike]

        # Record history
        snapshot = {
            "timestamp": datetime.now(UTC).isoformat(),
            "spot": spot,
            "n_nodes": len(self._nodes),
            "n_taps": len(new_taps),
            "nodes": [n.to_dict() for n in self._nodes.values()],
        }
        self._history.append(snapshot)

        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "new_taps": new_taps,
            "expired": expired,
            "active_count": sum(1 for n in self._nodes.values() if n.state == NodeState.ACTIVE),
            "tapped_count": sum(1 for n in self._nodes.values() if n.state == NodeState.TAPPED),
            "decaying_count": sum(1 for n in self._nodes.values() if n.state == NodeState.DECAYING),
            "total_nodes": len(self._nodes),
        }

    def get_state(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "total_nodes": len(self._nodes),
            "history_length": len(self._history),
        }

    def to_dict(self) -> dict[str, Any]:
        """Full tracker snapshot for durable storage."""
        return {
            "tap_threshold_pct": self.tap_threshold_pct,
            "max_taps": self.max_taps,
            "max_nodes": self.max_nodes,
            "nodes": [n.to_dict() for n in self._nodes.values()],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> NodeLifecycleTracker:
        """Rehydrate a tracker (restart recovery). None/empty -> fresh."""
        d = d or {}
        t = cls(
            tap_threshold_pct=float(d.get("tap_threshold_pct", 0.003)),
            max_taps=int(d.get("max_taps", 5)),
            max_nodes=int(d.get("max_nodes", 20)),
        )
        for nd in d.get("nodes", []):
            try:
                node = Node.from_dict(nd)
                t._nodes[node.strike] = node
            except (KeyError, ValueError, TypeError):
                continue
        return t
