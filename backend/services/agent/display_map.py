"""Resolve display selections against an exact server cache version, never client values."""

import hashlib
import re
from datetime import datetime

from services.agent.contracts import canonical, fact, finite, instant
from services.market_provenance import spot_provenance


def map_cache_key(ticker, query):
    fields = {"expiries", "mode", "dte", "scalp", "withTaps", "maxStrikes"}
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker) or not isinstance(query, dict) or set(query) != fields:
        raise ValueError("Invalid map selection")
    for field, low, high in (("expiries", 1, 24), ("maxStrikes", 1, 512)):
        if type(query[field]) is not int or not low <= query[field] <= high:
            raise ValueError("Invalid map bounds")
    if query["mode"] not in {"day", "swing", "scalp"}:
        raise ValueError("Invalid map mode")
    if query["dte"] is not None and (type(query["dte"]) is not int or not 0 <= query["dte"] <= 3660):
        raise ValueError("Invalid map expiry range")
    if any(type(query[k]) is not bool for k in ("scalp", "withTaps")):
        raise ValueError("Invalid map flags")
    return f"{ticker}:{query['expiries']}:{query['mode']}:{query['dte']}:{query['scalp']}:{query['withTaps']}:{query['maxStrikes']}"


def number(value):
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        result = float(value)
        return result if finite(result) else None
    except (TypeError, ValueError):
        return None


def display_facts(raw, screen, ticker, now):
    if not screen.get("mapQuery"):
        return [], ["The displayed map has no verified request scope"] if "mapVersion" in screen else []
    missing = "The exact displayed map is unavailable or changed; its values were not substituted"
    try:
        key = map_cache_key(ticker, screen["mapQuery"])
        if not isinstance(raw, dict) or screen.get("ticker") != ticker or raw.get("ticker") != ticker:
            return [], [missing]
        version = instant(screen.get("mapVersion"))
        if version is None or instant(raw.get("asof")) != version:
            return [], [missing]
        if raw.get("map_query") != screen["mapQuery"]:
            return [], [missing]
        if screen.get("contextVersion") == 2:
            if any(screen.get(field) != expected or expected is None for field, expected in (
                ("snapshotId", raw.get("snapshotId") or raw.get("snapshot_id")),
                ("provider", raw.get("data_source")),
                ("formula", raw.get("formula_version") or (raw.get("metrics") or {}).get("formula_version")),
            )):
                return [], [missing]
            walls = (raw.get("metrics") or {}).get("walls") or []
            if screen.get("selectedWall") and not any(w.get("wall_id") == screen["selectedWall"] for w in walls):
                return [], ["The selected wall is not in this recorded observation"]
        grid = raw.get("grid") or {}
        strikes, expiries = screen.get("mapStrikes"), screen.get("mapExpiries")
        if (
            not isinstance(strikes, list)
            or not 1 <= len(strikes) <= 512
            or any(not finite(s) or s <= 0 for s in strikes)
            or len(set(strikes)) != len(strikes)
            or not isinstance(expiries, list)
            or not 1 <= len(expiries) <= 24
            or any(not isinstance(e, str) for e in expiries)
            or len(set(expiries)) != len(expiries)
        ):
            return [], [missing]
        available = {number(s) for s in grid.get("strikes", [])}
        if not set(strikes) <= available or not set(expiries) <= set(grid.get("expiries", [])):
            return [], [missing]
        metric = screen.get("metric", "gex")
        grid_key = {"gex": "grid", "skylit": "grid", "vex": "vex_grid", "charm": "charm_grid"}.get(metric)
        if not grid_key or not isinstance(grid.get(grid_key), dict):
            return [], ["The selected display measure is unavailable"]
        matrix = grid[grid_key]
        scope = hashlib.sha256(canonical([key, strikes, expiries, metric]).encode()).hexdigest()
        identity = hashlib.sha256(canonical([raw, scope]).encode()).hexdigest()
        observed = instant(raw.get("event_time") or raw.get("observed_at"))
        status, gaps = "ok", []
        if observed is None:
            status = "degraded"
            gaps.append("Displayed map source observation time is unknown")
        elif not -30 <= (now - datetime.fromisoformat(observed)).total_seconds() <= 120:
            status = "stale"
            gaps.append("Displayed map source observation is stale or has an invalid future time")
        if raw.get("stale") or (finite(raw.get("stale_age_s")) and raw["stale_age_s"] > 120):
            status = "stale"
            gaps.append("Displayed map is marked out of date")
        facts = []

        def add(label, value, unit, whole_map=False, **kw):
            facts.append(
                fact(
                    label,
                    value,
                    unit,
                    ticker=ticker,
                    source=str(raw.get("source") or raw.get("data_source") or "cached dealer map"),
                    snapshot_id=identity,
                    event_time=observed,
                    received_at=raw.get("fetched_at"),
                    horizon=("map:" + hashlib.sha256(key.encode()).hexdigest()) if whole_map else "display:" + scope,
                    status=status,
                    **kw,
                )
            )

        def cell(expiry, strike):
            col = matrix.get(expiry) or {}
            return number(col.get(str(int(strike)) if float(strike).is_integer() else str(strike)))

        add("Displayed strikes", strikes, "USD")
        add("Displayed expiry dates", expiries, "dates")
        spot = number(raw.get("spot"))
        if spot is not None and spot > 0:
            facts.append(fact(
                "Cached map price",
                spot,
                "USD",
                ticker=ticker, snapshot_id=identity,
                horizon="map:" + hashlib.sha256(key.encode()).hexdigest(),
                **spot_provenance(raw, now, max_age=120),
                reason="Price from the cached map; a separate live quote may differ",
            ))
        flip = number((raw.get("gamma_flip") or {}).get("gamma_flip"))
        if screen.get("page") == "heatseeker" and raw.get("flip_zones"):
            first = raw["flip_zones"][0].get("price")
            if first is not None:
                flip = number(first)
        if flip is not None and flip > 0:
            add(
                "Displayed flip",
                flip,
                "USD",
                whole_map=True,
                reason="Map-level estimate; not recomputed for visible rows or the question's expiry filter",
            )
        else:
            gaps.append("The displayed map has no verified flip level")
        unit = "display gamma units" if metric in {"gex", "skylit"} else f"display {metric} units"
        selected_strike, selected_expiry = screen.get("selectedStrike"), screen.get("selectedExpiry")
        if finite(selected_strike) and selected_strike in strikes and selected_expiry in expiries:
            value = cell(selected_expiry, selected_strike)
            if value is not None:
                add("Selected display cell", value, unit, contract=f"{selected_expiry}:{selected_strike}:{metric}")
            else:
                gaps.append("The selected display cell has no reading")
        if screen.get("contextVersion") == 2:
            if screen.get("overlayMetric", "raw") != "raw" or screen.get("displayMode", "live") != "live":
                return [], ["Adjusted/replay evidence resolution remains unavailable"]
            add("Display basis", "Raw OI" if metric in {"gex", "skylit"} else metric.upper(), "basis")
            profile = []
            for strike in strikes:
                values = [cell(e, strike) for e in expiries]
                profile.append(None if any(v is None for v in values) else sum(values))
            add("Displayed signed profile", profile, unit)
            if any(v is None for v in profile):
                gaps.append("Missing cells remain gaps in the signed profile")
            wall = next((w for w in (raw.get("metrics") or {}).get("walls", [])
                         if w.get("wall_id") == screen.get("selectedWall")), None)
            if wall:
                for key, label, units in (("gross", "Selected raw wall gross", "USD/1% spot move"),
                                          ("net", "Selected raw wall net", "USD/1% spot move"),
                                          ("low", "Selected wall lower bound", "USD"),
                                          ("high", "Selected wall upper bound", "USD")):
                    if finite(wall.get(key)):
                        add(label, wall[key], units, whole_map=True, contract=wall["wall_id"])
            if screen.get("selectedContract"):
                gaps.append("Exact contract evidence is not admitted to model answers yet; inspect the read-only contract drawer")
        if screen.get("page") == "flowseeker-pro" and metric == "gex":
            # The dealer chart sums each shown expiry, in ascending strike order.
            if strikes != sorted(strikes):
                return [], [missing]
            net, cumulative, total = [], [], 0
            for strike in strikes:
                cells = [cell(e, strike) for e in expiries]
                value = None if any(v is None for v in cells) else sum(cells)
                total = None if value is None or total is None else total + value
                net.append(value)
                cumulative.append(total)
            add("Displayed net gamma", net, unit)
            add("Displayed cumulative gamma", cumulative, unit)
            if total is not None:
                add("Displayed total gamma", total, unit)
            else:
                gaps.append("Missing display cells prevent a complete cumulative total")
        return facts, gaps
    except (TypeError, ValueError, AttributeError):
        return [], [missing]
