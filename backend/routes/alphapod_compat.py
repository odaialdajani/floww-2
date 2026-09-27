"""AlphaPod-frontend compatibility router.

Provides API endpoints that the AlphaPod SPA expects, mapping them to floww
data sources. These are intentionally thin wrappers — they shape floww output
to the JSON contract the AlphaPod frontend bundle was built against.

Endpoints:
  GET /api/alpha-flow              — daily top-flow summary + market context
  GET /api/alpha-flow/dates        — list of available session dates
  GET /api/flow-digest             — daily executive digest
  GET /api/deep-dive/{ticker}      — per-ticker deep dive (chain + advanced)
  GET /api/gex/spx                 — SPX GEX snapshot in AlphaPod shape
  GET /api/earnings                — earnings calendar (stub)
  GET /api/earnings/week           — weekly earnings (stub)
  GET /api/earnings/ticker/{t}/detail — per-ticker earnings detail (stub)
  GET /api/flow-alerts             — flow alerts in AlphaPod shape (new path,
                                     mirrors /api/alerts shape for clients
                                     that prefer not to overload the rules ep)

The existing /api/alerts GET in server.py is extended in-place to also include
the AlphaPod keys (`alerts`, `page`, `page_size`, `total`) alongside the legacy
`rules`/`count` keys so existing tests keep passing.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api", tags=["alphapod-compat"])


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _shape_alert(rule_or_trigger: dict[str, Any], idx: int = 0) -> dict[str, Any]:
    """Reshape a floww alert rule/trigger into the AlphaPod flow-alert schema."""
    t = rule_or_trigger
    ticker = (t.get("ticker") or "SPY").upper()
    return {
        "alert_id": str(t.get("id") or t.get("rule_id") or idx + 1),
        "ticker": ticker,
        "option_type": t.get("option_type", "CALL"),
        "strike": float(t.get("strike") or 0),
        "expiration": t.get("expiry") or t.get("expiration") or _today_iso(),
        "dte": int(t.get("dte") or 0),
        "premium": float(t.get("premium") or 0),
        "size": int(t.get("size") or 0),
        "side": t.get("side", "BUY"),
        "alert_rule": t.get("alert_type") or t.get("type") or "manual",
        "has_sweep": bool(t.get("has_sweep", False)),
        "has_floor": bool(t.get("has_floor", False)),
        "volume": int(t.get("volume") or 0),
        "open_interest": int(t.get("open_interest") or 0),
        "vol_oi_ratio": float(t.get("vol_oi_ratio") or 0),
        "spot_price": float(t.get("spot_price") or t.get("spot") or 0),
        "sector": t.get("sector", ""),
        "tier": t.get("tier", "standard"),
        "iv": float(t.get("iv") or 0),
        "sentiment": t.get("sentiment", "neutral"),
        "exec_type": t.get("exec_type", "regular"),
        "confidence": t.get("confidence", "medium"),
        "confidence_score": float(t.get("confidence_score") or 0.5),
        "created_at": t.get("triggered_at") or t.get("created_at") or _now_iso(),
        "direction": t.get("direction", "neutral"),
    }


@router.get("/flow-alerts")
async def flow_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    ticker: str | None = None,
) -> dict[str, Any]:
    """AlphaPod-shape flow alerts. Backed by floww alert history."""
    # Lazy import to avoid module-level cycle with server.py.
    from server import _alert_history, _alert_rules

    source: list[dict[str, Any]] = list(_alert_history) or list(_alert_rules)
    if ticker:
        tu = ticker.upper()
        source = [s for s in source if (s.get("ticker") or "").upper() == tu]

    shaped = [_shape_alert(s, i) for i, s in enumerate(source)]
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "alerts": shaped[start:end],
        "page": page,
        "page_size": page_size,
        "total": len(shaped),
    }


# ----- Alpha Flow (daily top flow summary) ---------------------------------

_TOP10_FALLBACK = [
    {"rank": i + 1, "ticker": tk, "score": round(95 - i * 3.7, 2), "direction": dr}
    for i, (tk, dr) in enumerate(
        [
            ("SPY", "bullish"), ("QQQ", "bullish"), ("NVDA", "bullish"),
            ("TSLA", "bearish"), ("AAPL", "neutral"), ("MSFT", "bullish"),
            ("AMD", "bullish"), ("META", "neutral"), ("AMZN", "bullish"),
            ("GOOGL", "neutral"),
        ]
    )
]


@router.get("/alpha-flow")
async def alpha_flow(date_str: str | None = Query(None, alias="date")) -> dict[str, Any]:
    """Daily top-flow summary. Maps floww flowseeker output to AlphaPod schema."""
    session_date = date_str or _today_iso()
    spy_close = 0.0
    vix_close = 0.0
    top_10: list[dict[str, Any]] = []

    # Pull live flowseeker if available — fall back to deterministic stub.
    try:
        from routes.flowseeker import live as flowseeker_live  # type: ignore
        live_payload = await flowseeker_live()  # type: ignore[misc]
        rows = (live_payload or {}).get("symbols") or (live_payload or {}).get("rows") or []
        for i, row in enumerate(rows[:10]):
            top_10.append({
                "rank": i + 1,
                "ticker": (row.get("symbol") or row.get("ticker") or "").upper(),
                "score": float(row.get("score") or row.get("composite") or 0),
                "direction": row.get("direction") or row.get("bias") or "neutral",
            })
    except Exception:
        top_10 = list(_TOP10_FALLBACK)

    return {
        "session_date": session_date,
        "market": {"spy_close": spy_close, "vix_close": vix_close},
        "title": f"Alpha Flow — {session_date}",
        "executive_summary_md": (
            f"## Alpha Flow — {session_date}\n\n"
            "Top 10 tickers by composite flow score. Live data when the "
            "flowseeker provider is healthy, otherwise a deterministic stub."
        ),
        "top_10": top_10 or list(_TOP10_FALLBACK),
    }


@router.get("/alpha-flow/dates")
async def alpha_flow_dates() -> dict[str, Any]:
    """List of historical session dates available. Stub: trailing 30 weekdays."""
    today = date.today()
    days: list[str] = []
    d = today
    while len(days) < 30:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return {"dates": days, "count": len(days)}


# ----- Daily Digest --------------------------------------------------------


@router.get("/flow-digest")
async def flow_digest(date_str: str | None = Query(None, alias="date")) -> dict[str, Any]:
    """Daily digest. Wraps briefing if available."""
    session_date = date_str or _today_iso()
    body_md = ""
    try:
        from routes.briefing import daily_briefing  # type: ignore
        b = await daily_briefing()  # type: ignore[misc]
        body_md = (b or {}).get("markdown") or (b or {}).get("body_md") or ""
    except Exception:
        body_md = ""

    if not body_md:
        body_md = (
            f"# Flow Digest — {session_date}\n\n"
            "_Live briefing unavailable; showing scaffold._\n\n"
            "- Top flow tickers: SPY, QQQ, NVDA\n"
            "- VIX regime: normal\n"
            "- Gamma regime: positive\n"
        )
    return {
        "session_date": session_date,
        "title": f"Daily Flow Digest — {session_date}",
        "body_md": body_md,
        "created_at": _now_iso(),
    }


# ----- Deep Dive (per-ticker) ----------------------------------------------


@router.get("/deep-dive/{ticker}")
async def deep_dive(ticker: str) -> dict[str, Any]:
    """Per-ticker deep dive. Combines chain + advanced analytics."""
    t = ticker.strip().upper()
    chain_data: dict[str, Any] = {}
    advanced_data: dict[str, Any] = {}

    try:
        # Reach into server.py for the merged chain fetcher.
        from server import fetch_spot_and_chains_merged  # type: ignore
        chain_data = await fetch_spot_and_chains_merged(t, 4)
    except Exception as e:
        chain_data = {"error": f"chain fetch failed: {e}"}

    spot = chain_data.get("spot") or 0
    contracts = chain_data.get("contracts") or []

    summary = {
        "ticker": t,
        "spot": spot,
        "asof": _now_iso(),
        "n_contracts": len(contracts),
    }
    # Pull a few quick analytics if the helpers are available.
    try:
        from services.gex_core import compute_gex_by_strike
        gex_rows = compute_gex_by_strike(spot, contracts, t)
        summary["total_gex"] = sum(r.get("gex", 0) for r in gex_rows)
        summary["top_strikes"] = sorted(
            gex_rows, key=lambda r: abs(r.get("gex", 0)), reverse=True
        )[:5]
    except Exception:
        pass  # silent by design: legacy compat route; missing top-walls degrade to empty list

    return {
        "ticker": t,
        "session_date": _today_iso(),
        "summary": summary,
        "chain": {"spot": spot, "contracts": contracts[:200]},
        "advanced": advanced_data,
    }


# ----- SPX GEX --------------------------------------------------------------


@router.get("/gex/spx")
async def gex_spx() -> dict[str, Any]:
    """SPX GEX snapshot in AlphaPod shape."""
    try:
        from server import fetch_spot_and_chains_merged
        from services.gex_core import compute_gex_by_strike
        raw = await fetch_spot_and_chains_merged("^SPX", 4)
        spot = raw.get("spot") or 0
        rows = compute_gex_by_strike(spot, raw.get("contracts") or [], "^SPX")
        rows_sorted = sorted(rows, key=lambda r: r.get("strike", 0))
        total_gex = sum(r.get("gex", 0) for r in rows)
        resp: dict[str, Any] = {
            "ticker": "SPX",
            "spot": spot,
            "asof": _now_iso(),
            "by_strike": rows_sorted,
            "total_gex": total_gex,
        }
        # Paper-accurate Gamma Imbalance (Barbon-Buraschi)
        if spot > 0:
            try:
                from services.gex_paper_accurate import compute_gamma_imbalance
                resp["gamma_imbalance"] = compute_gamma_imbalance(total_gex, spot, 3_500_000)
            except Exception:
                pass  # silent by design: legacy compat route; gamma_imbalance field simply absent
        return resp
    except Exception as e:
        return {
            "ticker": "SPX",
            "spot": 0,
            "asof": _now_iso(),
            "by_strike": [],
            "total_gex": 0,
            "error": str(e),
        }


# ----- Earnings (stubs) -----------------------------------------------------


@router.get("/earnings")
async def earnings() -> dict[str, Any]:
    """Earnings calendar. Stub — floww has no native earnings data source."""
    return {"calendar": [], "asof": _now_iso(), "source": "stub"}


@router.get("/earnings/week")
async def earnings_week() -> dict[str, Any]:
    """Weekly earnings. Stub."""
    return {"week_of": _today_iso(), "events": [], "source": "stub"}


@router.get("/earnings/ticker/{ticker}/detail")
async def earnings_ticker_detail(ticker: str) -> dict[str, Any]:
    """Per-ticker earnings detail. Stub."""
    return {
        "ticker": ticker.upper(),
        "next_event": None,
        "history": [],
        "source": "stub",
    }


# ----- Dev Auth (local development only) ----------------------------------


@router.post("/auth/dev-token")
async def dev_token(body: dict[str, Any]) -> dict[str, Any]:
    """Issue a local dev JWT for the React frontend sign-in page.

    Dev-only: refuses with 403 unless the operator opts in with
    FLOWW_ALLOW_DEV_TOKENS=1. Never enable on a reachable deployment —
    this mints 24-hour tokens for arbitrary email/tier with no auth.
    """
    if os.environ.get("FLOWW_ALLOW_DEV_TOKENS", "") != "1":
        raise HTTPException(status_code=403, detail={
            "error": "dev_tokens_disabled",
            "message": ("Dev-token minting is disabled. Set "
                        "FLOWW_ALLOW_DEV_TOKENS=1 on a local dev backend only."),
        })
    import base64
    import hashlib
    import hmac
    import json as _json
    import time

    email = (body.get("email") or "dev@local").lower().strip()
    tier = (body.get("tier") or "pro").lower().strip()

    header = base64.urlsafe_b64encode(
        _json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        _json.dumps({
            "sub": email,
            "tier": tier,
            "iat": int(time.time()),
            # 24h, not 30d: dev tokens are convenience credentials for local
            # sign-in; a month-long pro-tier JWT is an unnecessary blast
            # radius if one leaks (endpoint itself is env-gated above).
            "exp": int(time.time()) + 86400,
            "iss": "floww-dev",
        }).encode()
    ).rstrip(b"=").decode()
    secret = os.environ.get("JWT_SECRET_KEY", "").encode()
    if not secret:
        raise HTTPException(status_code=503, detail="JWT secret not configured — set JWT_SECRET_KEY in environment")
    sig = base64.urlsafe_b64encode(
        hmac.new(secret, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()

    access_token = f"{header}.{payload}.{sig}"
    subscriber = {
        "email": email,
        "tier": tier,
        "display_name": email.split("@")[0],
    }
    return {"access_token": access_token, "subscriber": subscriber}
