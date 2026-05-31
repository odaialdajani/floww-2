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
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class NodeState(Enum):
    FORMED = "formed"
    ACTIVE = "active"
    TAPPED = "tapped"
    DECAYING = "decaying"
    EXPIRED = "expired"


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
        self.formation_time = datetime.now(timezone.utc)
        self.last_tap_time: Optional[datetime] = None
        self.tap_times: List[datetime] = []
        self.structural_weight = 1.0  # 1.0 = full strength, decays with taps
        self.opacity = 1.0  # visual opacity, decays with taps

    def check_tap(self, spot: float) -> bool:
        """Check if spot is within tap threshold of this node's strike."""
        threshold = self.strike * self.tap_threshold_pct
        return abs(spot - self.strike) <= threshold

    def tap(self):
        """Record a tap on this node."""
        now = datetime.now(timezone.utc)
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

    def update(self, spot: float):
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strike": self.strike,
            "gex_value": round(self.gex_value, 2),
            "state": self.state.value,
            "tap_count": self.tap_count,
            "structural_weight": round(self.structural_weight, 4),
            "opacity": round(self.opacity, 4),
            "formation_time": self.formation_time.isoformat(),
            "last_tap_time": self.last_tap_time.isoformat() if self.last_tap_time else None,
        }


class NodeLifecycleTracker:
    """Tracks the lifecycle of all King Nodes across time."""

    def __init__(self, tap_threshold_pct: float = 0.003, max_taps: int = 5,
                 max_nodes: int = 20):
        self.tap_threshold_pct = tap_threshold_pct
        self.max_taps = max_taps
        self.max_nodes = max_nodes
        self._nodes: Dict[float, Node] = {}  # strike -> Node
        self._history: deque = deque(maxlen=1000)

    def update(self, spot: float, king_nodes: List[Tuple[float, float]]) -> Dict[str, Any]:
        """Update all nodes with current spot and detected king nodes.

        Args:
            spot: current spot price
            king_nodes: list of (strike, gex_value) tuples

        Returns dict with active nodes, new taps, expired nodes, summary.
        """
        _current_strikes = {strike for strike, _ in king_nodes}

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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

    def get_state(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "total_nodes": len(self._nodes),
            "history_length": len(self._history),
        }
