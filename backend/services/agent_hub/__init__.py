"""
backend/services/agent_hub/__init__.py

Agent Hub — YAML-defined trading agent archetypes with trigger-based runtime.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

ARCHETYPES_DIR = Path(__file__).parent / "archetypes"


class AgentArchetype:
    """A single agent archetype loaded from YAML."""

    def __init__(self, config: Dict[str, Any]):
        self.name = config.get("name", "unnamed")
        self.description = config.get("description", "")
        self.triggers = config.get("triggers", [])
        self.logic = config.get("logic", "all")  # "all" | "any"
        self.action = config.get("action", {})
        self.enabled = config.get("enabled", False)
        self.last_fired: Optional[str] = None
        self.fire_count: int = 0

    def evaluate(self, metrics: Dict[str, float]) -> bool:
        """Evaluate triggers against current metrics. Returns True if fired."""
        if not self.enabled or not self.triggers:
            return False

        results = []
        for trigger in self.triggers:
            metric_name = trigger.get("metric", "")
            op = trigger.get("op", "gt")
            threshold = trigger.get("value", 0.0)
            current = metrics.get(metric_name)
            if current is None:
                results.append(False)
                continue
            if op == "gt":
                results.append(current > threshold)
            elif op == "lt":
                results.append(current < threshold)
            elif op == "eq":
                results.append(abs(current - threshold) < 0.001)
            else:
                results.append(False)

        if self.logic == "all":
            return all(results) if results else False
        return any(results)  # "any"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "logic": self.logic,
            "action": self.action,
            "enabled": self.enabled,
            "last_fired": self.last_fired,
            "fire_count": self.fire_count,
        }


class AgentHubRuntime:
    """Runtime that evaluates all enabled archetypes on each snapshot."""

    def __init__(self):
        self.archetypes: Dict[str, AgentArchetype] = {}
        self._load_defaults()

    def _load_defaults(self):
        """Load default archetypes from YAML files."""
        if ARCHETYPES_DIR.exists():
            for yaml_file in ARCHETYPES_DIR.glob("*.yaml"):
                try:
                    with open(yaml_file) as f:
                        config = yaml.safe_load(f)
                    if config:
                        archetype = AgentArchetype(config)
                        self.archetypes[archetype.name] = archetype
                        logger.info(f"Loaded archetype: {archetype.name}")
                except Exception as e:
                    logger.warning(f"Failed to load {yaml_file}: {e}")

    def register(self, config: Dict[str, Any]):
        """Register a new archetype."""
        archetype = AgentArchetype(config)
        self.archetypes[archetype.name] = archetype

    def unregister(self, name: str):
        """Remove an archetype."""
        self.archetypes.pop(name, None)

    def evaluate_all(self, metrics: Dict[str, float]) -> List[Dict[str, Any]]:
        """Evaluate all enabled archetypes. Returns list of fired actions."""
        from datetime import datetime, timezone
        fired = []
        for name, archetype in self.archetypes.items():
            if archetype.evaluate(metrics):
                archetype.last_fired = datetime.now(timezone.utc).isoformat()
                archetype.fire_count += 1
                fired.append({
                    "archetype": name,
                    "action": archetype.action,
                    "timestamp": archetype.last_fired,
                })
        return fired

    def get_status(self) -> Dict[str, Any]:
        return {
            "total": len(self.archetypes),
            "enabled": sum(1 for a in self.archetypes.values() if a.enabled),
            "archetypes": {name: a.to_dict() for name, a in self.archetypes.items()},
        }
