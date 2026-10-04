"""Constrained stored-cell observations, not range production/contract admission.

The producer's top-level metrics summary is unbound; raw population accounting
uses a different kernel. Neither is evidence here. A checked content digest is
only a consistency check, not proof of origin, population validity or authority.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from services.agent.contracts import fact, finite, instant
from services.solstice_range_analytics import compute_content_digest, record_id_for_digest

VERSION = "range-analytics.v1"
UNIT = "USD per 1% spot move (S^2 dealer-positive convention)"
IDENTITIES = {
    "raw_oi": ("gex_net_v1", "OI", "black_scholes_gamma(display S^2)"),
    "delta_weighted": ("dadgex_net_v1", "OI_DELTA_WEIGHTED", "vendor_gamma(|delta|)"),
    "volume": ("volume_gamma_v1", "VOLUME", "vendor_gamma(session volume)"),
    "window": ("window_dadgex_v1", "VOLUME_WINDOW", "recorded baseline required"),
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def count(value):
    return type(value) is int and value >= 0


def strike_key(value):
    require(finite(value) and value > 0, "RANGE_SELECTION_MISMATCH")
    return str(int(value)) if float(value).is_integer() else str(float(value))


def iso_date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except (ValueError, TypeError):
        return False


def query_valid(query):
    if not isinstance(query, dict) or set(query) != {"min_dte", "max_dte", "as_of_ny"}:
        return False
    if not (count(query["min_dte"]) and count(query["max_dte"])
            and query["min_dte"] <= query["max_dte"] <= 365):
        return False
    try:
        return date.fromisoformat(query["as_of_ny"]).isoformat() == query["as_of_ny"]
    except (ValueError, TypeError):
        return False


def validate_selection(screen):
    import re

    require(screen.get("contextVersion") == 2 and screen.get("page") == "heatseeker"
            and screen.get("activePane") == "gex" and screen.get("metric") == "gex"
            and screen.get("rangeVersion") == VERSION,
            "RANGE_CONTEXT_INVALID")
    rid, digest = screen.get("rangeRecordId"), screen.get("rangeDigest")
    require(isinstance(rid, str) and re.fullmatch(r"rga1-[a-f0-9]{24}", rid)
            and isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest)
            and rid == record_id_for_digest(digest) and screen.get("snapshotId") == rid,
            "RANGE_IDENTITY_MISMATCH")
    metric = screen.get("rangeMetric")
    require(isinstance(metric, str) and metric in IDENTITIES
            and screen.get("overlayMetric") == metric, "RANGE_METRIC_MISMATCH")
    require(screen.get("rangeBasis") == IDENTITIES[metric][1]
            and screen.get("formula") == "gex.v2"
            and screen.get("rangeStatus") in ("ok", "partial", "unavailable"), "RANGE_METRIC_MISMATCH")
    query = screen.get("mapQuery")
    require(query_valid(query), "RANGE_QUERY_INVALID")
    bounds = screen.get("expiryRange")
    require(bounds is None or bounds == [None, None] or
            isinstance(bounds, list) and len(bounds) == 2 and all(count(v) for v in bounds)
            and bounds == [query["min_dte"], query["max_dte"]], "RANGE_SCOPE_MISMATCH")
    strikes = screen.get("mapStrikes")
    require(isinstance(strikes, list) and 1 <= len(strikes) <= 512
            and all(finite(k) and k > 0 for k in strikes)
            and strikes == sorted(set(strikes)), "RANGE_AXES_INVALID")
    require(screen.get("selectedContract") is None and screen.get("selectedWall") is None
            and screen.get("contractResolution") == "RANGE_CONTRACT_UNAVAILABLE",
            "RANGE_CONTRACT_UNAVAILABLE")
    selected = screen.get("selectedStrike"), screen.get("selectedExpiry")
    require((selected == (None, None)) or (finite(selected[0]) and selected[0] in strikes
            and selected[1] in screen.get("mapExpiries", [])), "RANGE_SELECTION_MISMATCH")


def _validate(raw, screen, ticker):
    require(raw is not None, "RANGE_RECORD_UNAVAILABLE")
    require(isinstance(raw, dict), "RANGE_RECORD_CORRUPT")
    if raw.get("error"):
        reason = {
            "ROW_HEADER_MISMATCH": "RANGE_HEADER_MISMATCH",
            "DIGEST_MISMATCH": "RANGE_DIGEST_MISMATCH",
            "STORED_DIGEST_MISMATCH": "RANGE_DIGEST_MISMATCH",
            "RECORD_ID_MISMATCH": "RANGE_IDENTITY_MISMATCH",
            "INCOMPATIBLE_CONTENT_SCHEMA": "RANGE_SCHEMA_MISMATCH",
            "STORE_READ_FAILED": "RANGE_READ_UNAVAILABLE",
        }.get(str(raw["error"]), "RANGE_RECORD_CORRUPT")
        raise ValueError(reason)
    require(isinstance(raw.get("envelope"), dict), "RANGE_RECORD_CORRUPT")
    env = raw["envelope"]
    require(env.get("version") == VERSION and env.get("content_schema") == "rga-content.v2",
            "RANGE_SCHEMA_MISMATCH")
    digest = compute_content_digest(env)
    require(env.get("content_digest") == digest, "RANGE_DIGEST_MISMATCH")
    rid = record_id_for_digest(digest)
    require(env.get("record_id") == rid and screen.get("rangeRecordId") == rid
            and screen.get("snapshotId") == rid and screen.get("rangeDigest") == digest,
            "RANGE_IDENTITY_MISMATCH")
    q, clocks = env.get("query"), env.get("clocks")
    require(query_valid(q) and isinstance(clocks, dict), "RANGE_RECORD_CORRUPT")
    window = raw.get("window")
    require(isinstance(window, dict) and all(count(window.get(k)) for k in ("min_dte", "max_dte")),
            "RANGE_HEADER_MISMATCH")
    require(raw.get("record_id") == rid and raw.get("digest") == digest
            and raw.get("ticker") == env.get("symbol") == ticker == screen.get("ticker")
            and raw.get("window") == {k: q[k] for k in ("min_dte", "max_dte")}
            and raw.get("asof_date") == q["as_of_ny"]
            and raw.get("status") == env.get("status")
            and raw.get("received_at") == clocks.get("received_at"), "RANGE_HEADER_MISMATCH")
    require(env.get("status") in {"ok", "partial"}, "RANGE_RECORD_UNAVAILABLE")
    received = instant(clocks.get("received_at"))
    require(received is not None and datetime.fromisoformat(received).astimezone(
        ZoneInfo("America/New_York")).date().isoformat() == q["as_of_ny"], "RANGE_CLOCK_INVALID")
    for key in ("chain_event_time", "fetched_at"):
        require(clocks.get(key) is None or instant(clocks[key]) is not None, "RANGE_CLOCK_INVALID")
    event = instant(clocks.get("chain_event_time"))
    require(event is None or event <= received, "RANGE_CLOCK_INVALID")
    oi_dates = clocks.get("oi_effective_dates")
    if oi_dates is not None:
        require(isinstance(oi_dates, list) and len(oi_dates) <= 512
                and all(iso_date(d) and d <= q["as_of_ny"] for d in oi_dates)
                and oi_dates == sorted(set(oi_dates)), "RANGE_CLOCK_INVALID")
    axes = env.get("axes")
    require(isinstance(axes, dict), "RANGE_AXES_INVALID")
    rows, keys = axes.get("expiries"), axes.get("strike_keys")
    require(isinstance(rows, list) and 1 <= len(rows) <= 24
            and isinstance(keys, list) and 1 <= len(keys) <= 512
            and all(isinstance(k, str) for k in keys), "RANGE_AXES_INVALID")
    require(count(axes.get("n_strikes")) and axes["n_strikes"] == len(keys)
            and keys == sorted(set(keys), key=float)
            and all(strike_key(float(k)) == k for k in keys), "RANGE_AXES_INVALID")
    expiries = []
    for row in rows:
        require(isinstance(row, dict) and count(row.get("dte"))
                and q["min_dte"] <= row["dte"] <= q["max_dte"], "RANGE_AXES_INVALID")
        exp = row.get("expiry")
        require(iso_date(exp)
                and (date.fromisoformat(exp) - date.fromisoformat(q["as_of_ny"])).days == row["dte"],
                "RANGE_AXES_INVALID")
        expiries.append(exp)
    require(expiries == sorted(set(expiries)), "RANGE_AXES_INVALID")
    coverage = env.get("coverage")
    require(isinstance(coverage, dict) and all(count(coverage.get(k)) for k in (
        "n_listed", "n_admitted", "n_returned_expiries", "n_skipped_expiries", "n_contracts"))
        and coverage["n_admitted"] == len(expiries) <= coverage["n_listed"]
        and coverage["n_returned_expiries"] + coverage["n_skipped_expiries"] == len(expiries)
        and type(coverage.get("complete")) is bool
        and coverage.get("requested_window") == {k: q[k] for k in ("min_dte", "max_dte")},
        "RANGE_COVERAGE_INVALID")
    skipped = coverage.get("skipped")
    require(isinstance(skipped, list) and len(skipped) == coverage["n_skipped_expiries"]
            and all(isinstance(s, dict) and s.get("expiry") in expiries for s in skipped)
            and len({s["expiry"] for s in skipped}) == len(skipped), "RANGE_COVERAGE_INVALID")
    if coverage["complete"]:
        require(not skipped and coverage.get("listing_capped") is False
                and coverage.get("lower_edge_observed") is True and coverage.get("upper_edge_observed") is True
                and coverage.get("complete_reason") is None, "RANGE_COVERAGE_INVALID")
    grounding = env.get("grounding")
    require(isinstance(grounding, dict) and grounding.get("resolver") == "range-resolver.v1"
            and grounding.get("record_query_identity") == {"symbol": ticker, **q}, "RANGE_IDENTITY_MISMATCH")
    grids, registry = env.get("grids"), env.get("metric_registry")
    require(isinstance(grids, dict) and isinstance(registry, dict)
            and set(grids) == set(registry) == set(IDENTITIES), "RANGE_METRIC_MISMATCH")
    for name, (metric_id, basis, model) in IDENTITIES.items():
        section = grids[name]
        expected = dict(metric_id=metric_id, basis=basis, formula_version="gex.v2", model=model, unit=UNIT)
        require(isinstance(section, dict) and registry[name] == expected
                and all(section.get(k) == v for k, v in expected.items())
                and section.get("status") in {"ok", "partial", "unavailable"}, "RANGE_METRIC_MISMATCH")
        cells = section.get("cells")
        require(isinstance(cells, dict) and set(cells) == set(expiries), "RANGE_GRID_INVALID")
        available = 0
        for exp in expiries:
            require(isinstance(cells[exp], dict) and set(cells[exp]) == set(keys), "RANGE_GRID_INVALID")
            for value in cells[exp].values():
                require(value is None or finite(value), "RANGE_GRID_INVALID")
                available += value is not None
        require(all(count(section.get(k)) for k in ("n_cells", "n_available", "cell_gaps"))
                and section["n_cells"] == len(expiries) * len(keys)
                and section["n_available"] == available
                and section["cell_gaps"] == section["n_cells"] - available
                and (section["status"] != "unavailable" or available == 0)
                and (section["status"] != "ok" or available == section["n_cells"]), "RANGE_GRID_INVALID")
        population = section.get("population")
        require(isinstance(population, dict) and count(population.get("input_contracts"))
                and count(population.get("usable")) and count(section.get("usable"))
                and section["usable"] == population["usable"]
                and population["usable"] <= population["input_contracts"]
                and (available == 0 or population["usable"] > 0)
                and (name == "window" or population["input_contracts"] == coverage["n_contracts"]),
                "RANGE_POPULATION_INVALID")
        for key, value in population.items():
            if name == "raw_oi" and key == "zero_oi_or_excluded_by_kernel":
                # This unquantified, other-kernel population is explicitly NOT admitted.
                require(isinstance(value, str), "RANGE_POPULATION_INVALID")
            else:
                require(count(value) and value <= population["input_contracts"], "RANGE_POPULATION_INVALID")
    metric = screen["rangeMetric"]
    section = grids[metric]
    require(screen.get("mapQuery") == q and screen.get("mapExpiries") == expiries
            and [strike_key(k) for k in screen.get("mapStrikes", [])] == keys
            and screen.get("mapVersion") == clocks["received_at"]
            and screen.get("provider") == (env.get("provenance") or {}).get("data_source")
            and screen.get("formula") == section["formula_version"]
            and screen.get("rangeBasis") == section["basis"]
            and screen.get("rangeStatus") == section["status"]
            and (screen.get("observedAt") is None or instant(screen["observedAt"]) == instant(clocks.get("chain_event_time"))),
            "RANGE_SELECTION_MISMATCH")
    require(metric != "window", "RANGE_WINDOW_UNAVAILABLE")
    require(section["status"] != "unavailable", "RANGE_CELL_UNAVAILABLE")
    return env, section, expiries, keys


def range_snapshot(raw, screen, ticker, horizon, now):
    """Project only selected finite cells, preserving unknown event/OI clocks."""
    snapshot = dict(snapshot_id=screen.get("rangeRecordId"), ticker=ticker, horizon=horizon,
                    window={}, facts=[], gaps=[], alerts_status="not_requested", flow=[],
                    observed_at=None, captured_at=now.isoformat(), anchor_kind="recorded",
                    coverage=None, coverage_id=None, agreement={"total": None}, replay=True)
    try:
        env, section, expiries, keys = _validate(raw, screen, ticker)
        selected = screen.get("selectedExpiry")
        if selected is not None:
            key = strike_key(screen.get("selectedStrike"))
            require(selected in expiries and key in keys, "RANGE_SELECTION_MISMATCH")
            require(section["cells"][selected][key] is not None, "RANGE_CELL_UNAVAILABLE")
            cells = [(selected, key, section["cells"][selected][key])]
        else:
            cells = [(exp, key, section["cells"][exp][key]) for exp in expiries for key in keys
                     if section["cells"][exp][key] is not None]
            require(1 <= len(cells) <= 512, "RANGE_SELECTION_REQUIRED")
        clock, rid = env["clocks"], env["record_id"]
        notes = ["Stored cell observation; research only; no population/completeness or trading admission"]
        gaps = ["RANGE_RESEARCH_ONLY", "RANGE_PRODUCTION_INTEGRITY_HOLD", "RANGE_CONTRACT_UNAVAILABLE",
                "REPLAY_NOT_EXECUTABLE"]
        if screen["rangeMetric"] == "raw_oi":
            notes.append("Raw population uses a different kernel and is unverified")
            gaps.append("RANGE_RAW_POPULATION_MODEL_UNVERIFIED")
        if clock.get("chain_event_time") is None:
            notes.append("Chain event time unknown; received time is not observation time")
            gaps.append("RANGE_EVENT_TIME_UNKNOWN")
        if not clock.get("oi_effective_dates"):
            notes.append("OI effective date unknown")
            gaps.append("RANGE_OI_DATE_UNKNOWN")
        if env["status"] == "partial" or section["status"] == "partial":
            gaps.append("RANGE_PARTIAL_COVERAGE")
        if env.get("synthetic"):
            gaps.append("RANGE_SYNTHETIC_RECORD")
        facts = [fact(f"Recorded range cell {section['metric_id']} {exp} {key}", value, section["unit"],
                      ticker=ticker, source=f"stored range/{screen['provider']}/{section['model']}",
                      snapshot_id=rid, event_time=clock.get("chain_event_time"),
                      received_at=clock["received_at"], horizon=horizon, contract=None,
                      status="degraded", reason="; ".join(notes),
                      version=f"{VERSION}/{section['metric_id']}/{section['basis']}/{section['formula_version']}")
                 for exp, key, value in cells]
        snapshot.update(facts=facts, gaps=gaps, observed_at=instant(clock.get("chain_event_time")),
                        window=dict(requested=horizon, start=expiries[0], end=expiries[-1],
                                    as_of_ny=env["query"]["as_of_ny"], **{k: env["query"][k] for k in ("min_dte", "max_dte")}),
                        range_observation=dict(record_id=rid, content_digest=env["content_digest"],
                                               metric_id=section["metric_id"], basis=section["basis"],
                                               model=section["model"], formula=section["formula_version"],
                                               unit=section["unit"], status=section["status"],
                                               query=env["query"], received_at=clock["received_at"],
                                               event_time=clock.get("chain_event_time"),
                                               oi_effective_dates=clock.get("oi_effective_dates"),
                                               production_admitted=False))
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("RANGE_") else "RANGE_RECORD_CORRUPT"
        snapshot["gaps"] = [reason + "; no substitute was read"]
    return snapshot
