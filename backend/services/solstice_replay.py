"""Recorded display projection for research; never reconstruct from present-day sources."""
import math
from copy import deepcopy

from services.agent.display_map import map_cache_key


def recorded_display(rep, ticker, snapshot_id):
    if not isinstance(rep, dict):
        return None
    snap, ctx = rep.get("snapshot") or {}, rep.get("context") or {}
    if snap.get("ticker") != ticker or snap.get("snapshot_id") != snapshot_id:
        return None
    display = ctx.get("display") or {}
    query = display.get("map_query")
    try:
        map_cache_key(ticker, query)
    except (ValueError, TypeError):
        return None
    grids = rep.get("grids") or {}
    main = grids.get("grid") or {}
    if not isinstance(main.get("grid"), dict) or not isinstance(rep.get("metrics_full"), dict):
        return None
    return deepcopy(dict(
        ticker=ticker, snapshotId=snapshot_id, recorded_snapshot_id=snapshot_id, replay=True,
        asof=snap.get("asof_ts"), spot=snap.get("spot"), data_source=snap.get("data_source"),
        formula_version=snap.get("formula_version"), exposure_basis=snap.get("exposure_basis"), map_query=query,
        scope_selection=display.get("scope_selection"),
        event_time=display.get("event_time") or display.get("observed_at"),
        fetched_at=display.get("fetched_at"), spot_source=display.get("spot_source"),
        spot_event_time=display.get("spot_event_time"), spot_fetched_at=display.get("spot_fetched_at"),
        stale=display.get("stale"), stale_age_s=display.get("stale_age_s"),
        grid=dict(**{k: v for k, v in main.items() if k not in {"strikes", "expiries", "grid", "formula_version", "exposure_basis"}},
                  strikes=main.get("strikes") or [s["strike"] for s in rep.get("strikes", [])],
                  expiries=main.get("expiries") or list(main["grid"]), grid=main["grid"],
                  formula_version=main.get("formula_version"), exposure_basis=main.get("exposure_basis")),
        metrics={**rep["metrics_full"], "walls": rep.get("walls") or [],
                 "grids": {k: v for k, v in grids.items() if k not in {"grid", "version"} and isinstance(v, dict) and "grid" in v}},
        # Nullable DOUBLEs returned through pandas may be NaN. Preserve unknown
        # as null at this projection seam, never a numeric zero or live quote.
        contracts=[{key: None if isinstance(value, float) and not math.isfinite(value) else value
                    for key, value in row.items()} for row in rep.get("contracts") or []],
        contract_coverage=rep.get("coverage"),
        quality=rep.get("quality"), interactions=rep.get("interactions") or [], scenarios=rep.get("scenarios") or [],
    ))
