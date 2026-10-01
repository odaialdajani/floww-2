"""Resolve display selections against an exact server cache version, never client values."""

import hashlib
import re
from datetime import date, datetime

from domain.exposure_metrics import METRIC_REGISTRY
from services.agent.contracts import canonical, fact, finite, instant
from services.market_provenance import spot_provenance


def map_cache_key(ticker, query):
    fields = {"expiries", "mode", "dte", "scalp", "withTaps", "maxStrikes"}
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker) or not isinstance(query, dict) or set(query) not in (fields, fields | {"expiryScope", "sessionDate"}):
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
    if "expiryScope" in query:
        if (query["expiryScope"] != "next" or query["mode"] != "day" or query["dte"] is not None
                or query["scalp"] or not isinstance(query["sessionDate"], str)
                or date.fromisoformat(query["sessionDate"]).isoformat() != query["sessionDate"]):
            raise ValueError("Invalid next-listed scope")
    from services.solstice_scope import cache_key
    return cache_key(ticker, query)


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
        overlay = screen.get("overlayMetric", "raw")
        replay = screen.get("displayMode", "live") == "replay"
        v2 = screen.get("contextVersion") == 2
        if replay and (not v2 or raw.get("replay") is not True or raw.get("recorded_snapshot_id") != screen.get("snapshotId")):
            return [], ["Adjusted/replay evidence resolution remains unavailable"]
        if v2 and screen.get("displayMode", "live") not in {"live", "replay"}:
            return [], [missing]
        metric = screen.get("metric", "gex")
        metric_id = {"raw": "gex_net_v1", "delta": "dadgex_net_v1", "activity": "volume_gamma_v1",
                     "session_delta_volume": "session_delta_volume_gamma_v1", "window": "window_dadgex_v1"}.get(overlay)
        if overlay != "raw" and (not v2 or metric not in {"gex", "skylit"} or metric_id is None):
            return [], ["The selected adjusted basis is unavailable"]
        if v2:
            panes = ({"raw"} if overlay == "raw" else {"adjusted"}) if screen.get("page") == "trinity" else (
                ({"gex", "raw"} if metric in {"gex", "skylit"} else {"gex", metric}) if overlay == "raw" else {"gex", "delta", "adjusted"})
            if screen.get("activePane") not in panes:
                return [], ["Selected pane conflicts with its display basis"]
        window = None
        if overlay == "window":
            from services.agent.window_facts import window_evidence
            window, window_gaps = window_evidence(raw, screen, now)
            if window_gaps:
                return [], window_gaps
        grid = (raw.get("grid") or {}) if overlay == "raw" else ((raw.get("metrics") or {}).get("grids") or {}).get(overlay)
        if not isinstance(grid, dict) or grid.get("status") == "unavailable":
            return [], ["Adjusted/replay evidence resolution remains unavailable"]
        if overlay != "raw" and (grid.get("formula_version") != raw.get("formula_version")
                                  or grid.get("exposure_basis") != METRIC_REGISTRY[metric_id]["basis"]):
            return [], ["Adjusted surface provenance conflicts with the recorded observation"]
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
        if v2 and ((screen.get("selectedStrike") is not None and screen["selectedStrike"] not in strikes)
                   or (screen.get("selectedExpiry") is not None and screen["selectedExpiry"] not in expiries)):
            return [], ["Selected cell is outside the verified displayed scope"]
        grid_key = {"gex": "grid", "skylit": "grid", "vex": "vex_grid", "charm": "charm_grid"}.get(metric)
        if not grid_key or not isinstance(grid.get(grid_key), dict):
            return [], ["The selected display measure is unavailable"]
        if v2 and screen.get("selectedContract") is not None:
            from services.agent.contract_facts import contract_facts
            return contract_facts(raw, screen, ticker, now)
        matrix = grid[grid_key]
        scope = hashlib.sha256(canonical([key, strikes, expiries, metric, overlay, screen.get("activePane"),
                                          screen.get("selectedWall"), "replay" if replay else "live"]).encode()).hexdigest()
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
        if replay:
            status = "degraded"
            gaps.append("Recorded snapshot evidence only; not a live observation or current trading context")
        coverage = ((raw.get("metrics") or {}).get("surface_coverage") or {}).get(overlay) or {}
        if coverage.get("status") == "partial" or grid.get("status") == "partial":
            status = "degraded" if status == "ok" else status
            gaps.append("Displayed surface is partial; excluded observations were not filled with zero")
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

        if window:
            for field in ("start", "end"):
                add("Window interval " + field, window["interval"][field], "source timestamp")
            add("Window previous snapshot", window["comparison"]["previous_snapshot_id"], "observation identity")
            add("Window volume correction policy", window["comparison"]["volume_correction_policy"], "policy")
            add("Window Greek convention", window["greek_convention"], "convention")
            gaps.append("Two recorded observations only; " + window.get("provenance_note", "activity is not aggressor-signed flow"))
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
                **{**spot_provenance(raw, now, max_age=120), **({"status": "degraded"} if replay else {})},
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
        unit = (METRIC_REGISTRY[metric_id]["units"] if overlay != "raw" else
                "display gamma units" if metric in {"gex", "skylit"} else f"display {metric} units")
        selected_strike, selected_expiry = screen.get("selectedStrike"), screen.get("selectedExpiry")
        if finite(selected_strike) and selected_strike in strikes and selected_expiry in expiries:
            value = cell(selected_expiry, selected_strike)
            if value is not None:
                add("Selected display cell", value, unit, contract=f"{selected_expiry}:{selected_strike}:{metric}")
            else:
                gaps.append("The selected display cell has no reading")
        if v2:
            add("Display basis", METRIC_REGISTRY[metric_id]["basis"] if overlay != "raw" else
                "Raw OI" if metric in {"gex", "skylit"} else metric.upper(), "basis")
            profile, missing_delta, invalid_delta = [], [], []
            for strike in strikes:
                known = [v for e in expiries if (v := cell(e, strike)) is not None]
                profile.append(sum(known) if known else None)
                sk = str(int(strike)) if float(strike).is_integer() else str(strike)
                missing_delta.append(sum(((grid.get("cell_missing_delta") or {}).get(e) or {}).get(sk, 0) for e in expiries))
                invalid_delta.append(sum(((grid.get("cell_invalid_delta") or {}).get(e) or {}).get(sk, 0) for e in expiries))
            add("Displayed signed profile", profile, unit)
            add("Displayed profile missing delta", missing_delta, "excluded contracts")
            add("Displayed profile invalid delta", invalid_delta, "excluded contracts")
            if any(v is None for v in profile):
                gaps.append("Missing cells remain gaps in the signed profile")
            if any(missing_delta) or any(invalid_delta):
                gaps.append("Partial profile preserves valid contributions; missing and invalid delta remain distinct")
            wall = next((w for w in (raw.get("metrics") or {}).get("walls", [])
                         if w.get("wall_id") == screen.get("selectedWall")), None)
            if wall:
                for key, label, units in (("gross", "Selected raw wall gross", "USD/1% spot move"),
                                          ("net", "Selected raw wall net", "USD/1% spot move"),
                                          ("low", "Selected wall lower bound", "USD"),
                                          ("high", "Selected wall upper bound", "USD")):
                    if finite(wall.get(key)):
                        add(label, wall[key], units, whole_map=True, contract=wall["wall_id"])
                if finite(selected_strike) and not wall.get("low", selected_strike) <= selected_strike <= wall.get("high", selected_strike):
                    return [], ["Selected cell conflicts with its raw structural wall"]
                if overlay == "window":
                    row = ((raw.get("metrics") or {}).get("wall_window") or {}).get(wall["wall_id"]) or {}
                    value = number(row.get("window_daddex"))
                    if value is not None:
                        add("Selected adjusted wall net", value, unit, whole_map=True, contract=wall["wall_id"],
                            reason="Same raw wall over the recorded comparable window; not dealer intent or signed flow")
                    else:
                        gaps.append("Selected raw wall has no usable comparable window observation")
                elif overlay != "raw":
                    row = ((raw.get("metrics") or {}).get("wall_metrics") or {}).get(wall["wall_id"]) or {}
                    prefix = {"delta": "daddex", "activity": "volume", "session_delta_volume": "sdv"}[overlay]
                    if finite(row.get(prefix + "_usable")) and row[prefix + "_usable"] > 0:
                        for field in ("net", "gross"):
                            value = number(row.get(prefix + "_" + field))
                            if value is not None:
                                add("Selected adjusted wall " + field, value, unit, whole_map=True, contract=wall["wall_id"],
                                    reason="Same raw wall over the full recorded map scope; weighting is not dealer intent")
                        for field in ("missing", "invalid", "missing_delta"):
                            if row.get(prefix + "_" + field, 0):
                                gaps.append("Selected adjusted wall is partial; excluded members remain unknown or invalid")
                    else:
                        gaps.append("Selected raw wall has no usable adjusted observation")

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
