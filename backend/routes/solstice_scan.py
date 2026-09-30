"""Bounded, on-demand research scanner. No scheduler or legacy leaderboard writes."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from auth import require_api_key
from services import solstice_scan
from services.solstice_rank import RANK_VERSION, fuse_one

router = APIRouter(prefix="/api/solstice/scan", tags=["solstice"])


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    limit: int = Field(12, ge=1, le=20)
    max_expiries: int = Field(2, ge=1, le=4)
    dte: int | None = Field(None, ge=0, le=365)
    refresh: bool = False


def _delivery(out):
    result = dict(out)
    result.update(leaderboard=out.get("rows") or [], rank_method=RANK_VERSION,
                  calibration_state="unvalidated_research_ranking",
                  permission="read_only_research", durability="process_memory_only")
    try:
        at = datetime.fromisoformat(str(out.get("computed_at")).replace("Z", "+00:00"))
        age = (datetime.now(UTC) - at).total_seconds() if at.tzinfo else None
    except (TypeError, ValueError):
        age = None
    result["leaderboard_age_s"] = age
    return result


def _rank_observation(ticker, heat, opportunity):
    """Use existing stored alert evidence and registered producer output, never defaults."""
    from services.duckdb_engine import db
    from services.flow_alerts import read_alert_feed

    flow = None
    source = None
    try:
        alerts = read_alert_feed(db, days=7, ticker=ticker, sort_by="conviction")
        if alerts:
            source = alerts[0].get("asof_ts")
            flow = {"conviction": alerts[0].get("conviction"), "key": alerts[0].get("key")}
    except Exception:
        # An unavailable feed stays absent, not a measured zero.
        pass
    heat = heat or {}
    row = fuse_one(ticker, flow=flow, opportunity=opportunity,
                   snapshot_id=heat.get("snapshotId"), asof=heat.get("asof"))
    row["evidence"]["flow_asof"] = source
    row["evidence"]["provider"] = heat.get("data_source")
    row["evidence"]["formula_version"] = heat.get("formula_version")
    return row


@router.get("/leaderboard")
async def leaderboard(limit: int = Query(12, ge=1, le=20),
                      max_expiries: int = Query(2, ge=1, le=4),
                      dte: int | None = Query(None, ge=0, le=365)):
    return _delivery(solstice_scan.peek_scan(limit=limit, max_expiries=max_expiries, dte=dte))


@router.post("", dependencies=[Depends(require_api_key)])
async def scan(body: ScanRequest):
    # Existing coordinator delegates to scan_batch's shared PublicBudget and
    # canonical builder. No provider/client is constructed by this router.
    out = await solstice_scan.run_scan(
        **body.model_dump(), conviction_fn=_rank_observation,
        opportunity_fn=lambda _ticker, heat: (heat or {}).get("opportunity"),
    )
    return _delivery(out)
