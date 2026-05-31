"""
backend/services/alerts/engine.py

Alert engine with YAML-defined rules and ML-enriched predicates.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

log = logging.getLogger("alerts.engine")

ALERT_DEFINITIONS_DIR = Path(__file__).resolve().parent.parent / "alerts" / "definitions"


class AlertDefinition:
    """Parsed alert definition from YAML."""

    def __init__(self, data: Dict[str, Any]):
        self.id = data["id"]
        self.name = data.get("name", self.id)
        self.description = data.get("description", "")
        self.predicate = data["predicate"]
        self.priority = data.get("priority", "medium")
        self.cooldown_minutes = data.get("cooldown_minutes", 60)
        self.ml_enriched = data.get("ml_enriched", False)
        self.ml_model = data.get("ml_model", None)
        self.ml_threshold = data.get("ml_threshold", 0.65)
        self.actions = data.get("actions", ["log"])
        self.enabled = data.get("enabled", True)


class AlertEngine:
    """Evaluates alert predicates against current market state."""

    def __init__(self, db, ml_predict_fn=None):
        self.db = db
        self.ml_predict_fn = ml_predict_fn
        self.definitions: List[AlertDefinition] = []
        self._last_fired: Dict[str, datetime] = {}
        self._load_definitions()

    def _load_definitions(self):
        """Load alert definitions from YAML files."""
        if not ALERT_DEFINITIONS_DIR.exists():
            log.warning(f"Alert definitions dir not found: {ALERT_DEFINITIONS_DIR}")
            return

        for yaml_file in sorted(ALERT_DEFINITIONS_DIR.glob("*.yaml")):
            try:
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                if isinstance(data, list):
                    for item in data:
                        self.definitions.append(AlertDefinition(item))
                elif isinstance(data, dict):
                    self.definitions.append(AlertDefinition(data))
                log.info(f"Loaded alert definition from {yaml_file.name}")
            except Exception as e:
                log.error(f"Failed to load alert definition from {yaml_file}: {e}")

    def evaluate(self, ticker: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate all alert definitions against current context."""
        fired = []

        for definition in self.definitions:
            if not definition.enabled:
                continue

            # Check cooldown
            last_fired = self._last_fired.get(definition.id)
            if last_fired:
                cooldown = timedelta(minutes=definition.cooldown_minutes)
                if datetime.now(timezone.utc) - last_fired < cooldown:
                    continue

            # Evaluate predicate
            try:
                triggered = self._evaluate_predicate(definition, ticker, context)
            except Exception as e:
                log.error(f"Error evaluating alert {definition.id}: {e}")
                continue

            if triggered:
                alert = {
                    "id": definition.id,
                    "name": definition.name,
                    "priority": definition.priority,
                    "ticker": ticker,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "context": {k: v for k, v in context.items() if isinstance(v, (int, float, str, bool))},
                }
                fired.append(alert)
                self._last_fired[definition.id] = datetime.now(timezone.utc)
                self._persist_alert(alert)

        return fired

    def _evaluate_predicate(self, definition: AlertDefinition, ticker: str, context: Dict[str, Any]) -> bool:
        """Evaluate a single alert predicate."""
        predicate = definition.predicate

        if definition.ml_enriched and self.ml_predict_fn:
            # ML-enriched predicate: e.g., "ml.dir_1h_proba > 0.65"
            prediction = self.ml_predict_fn(ticker)
            if prediction:
                context["ml"] = prediction

        # Simple predicate evaluation
        # Supports: "field op value" format
        # e.g., "gex_total > 1000000", "spot > sma_20", "ml.dir_1h_proba > 0.65"
        try:
            return self._eval_expression(predicate, context)
        except Exception as e:
            log.error(f"Predicate evaluation error: {predicate}: {e}")
            return False

    def _eval_expression(self, expr: str, context: Dict[str, Any]) -> bool:
        """Evaluate a simple comparison expression."""
        expr = expr.strip()

        for op_str, op_func in [(">=", lambda a, b: a >= b),
                                 ("<=", lambda a, b: a <= b),
                                 ("!=", lambda a, b: a != b),
                                 (">", lambda a, b: a > b),
                                 ("<", lambda a, b: a < b),
                                 ("==", lambda a, b: a == b)]:
            if op_str in expr:
                parts = expr.split(op_str, 1)
                if len(parts) == 2:
                    left = self._resolve_value(parts[0].strip(), context)
                    right = self._resolve_value(parts[1].strip(), context)
                    return op_func(left, right)

        raise ValueError(f"Cannot parse expression: {expr}")

    def _resolve_value(self, key: str, context: Dict[str, Any]) -> Any:
        """Resolve a value from context or literal."""
        # Check context first
        if key in context:
            return context[key]

        # Try literal number BEFORE dot-split (handles "0.5", "100", etc.)
        try:
            return float(key)
        except ValueError:
            pass

        # Check nested (e.g., "ml.dir_1h_proba")
        if "." in key:
            parts = key.split(".")
            val = context
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    return None
            return val

        return key

    def _persist_alert(self, alert: Dict[str, Any]):
        """Persist fired alert to MongoDB."""
        try:
            self.db["alerts_history"].insert_one(alert)
        except Exception as e:
            log.error(f"Failed to persist alert: {e}")

    def reload(self):
        """Reload alert definitions from disk."""
        self.definitions.clear()
        self._load_definitions()
        log.info(f"Reloaded {len(self.definitions)} alert definitions")
