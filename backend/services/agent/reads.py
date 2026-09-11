"""Injected copy-only reads. No route, broker client or arbitrary network access."""

from __future__ import annotations

import asyncio
import copy
import hashlib
from datetime import UTC, datetime

from services.agent.access.horizon import horizon_window, slice_expiries
from services.agent.confluence import score
from services.agent.contracts import canonical, fact, finite, instant
from services.agent.display_map import display_facts
from services.agent.structure_reads import structure_facts
from services.agent.volatility_reads import volatility_facts
from services.heatseeker import _gex_per_strike, calc_flip_zones
from services.market_provenance import spot_provenance


class ResearchReads:
    def __init__(self, peek_chain, peek_map, read_alerts, *, read_daily_bars=None):
        self._peek_chain = peek_chain
        self._peek_map = peek_map
        self._read_alerts = read_alerts
        self._read_daily_bars = read_daily_bars

    async def snapshot(self, ticker, horizon, *, selected_expiry=None, now=None, screen=None, price_only=False):
        now = now or datetime.now(UTC)
        gaps = []
        daily_bars = None
        if not price_only and self._read_daily_bars is not None:
            try:
                daily_bars = copy.deepcopy(await asyncio.wait_for(
                    asyncio.to_thread(self._read_daily_bars, ticker), timeout=5))
                canonical(daily_bars)
            except Exception:
                daily_bars = None
                gaps.append("Daily bar cache could not be read; research did not refresh it")
        try:
            raw = copy.deepcopy(self._peek_chain(ticker, 6))
        except Exception:
            raw = None
            gaps.append("Chain cache could not be read")
        try:
            dealer = (
                copy.deepcopy(self._peek_map(ticker, screen["mapQuery"]))
                if not price_only and screen and screen.get("mapQuery")
                else None
            )
        except Exception:
            dealer = None
            gaps.append("Dealer cache could not be read")
        try:
            alerts = (
                [] if price_only else await asyncio.wait_for(asyncio.to_thread(self._read_alerts, ticker), timeout=5)
            )
            alerts_status = "not_requested" if price_only else "ok"
        except Exception:
            alerts, alerts_status = [], "error"
            gaps.append("Alert storage could not be read")
        window = horizon_window(horizon, now=now, selected_expiry=selected_expiry)
        if raw is None:
            raw = {}
            gaps.append("No cached option chain; research did not start a paid refresh")
        contracts = slice_expiries(raw.get("contracts") or [], horizon, now=now, selected_expiry=selected_expiry)
        if not contracts and not price_only:
            gaps.append("No contracts in the requested expiry range")
        source_time = instant(raw.get("event_time") or raw.get("observed_at"))
        quality = "degraded" if source_time is None else "ok"
        if source_time:
            age = (now - datetime.fromisoformat(source_time)).total_seconds()
            if age < -30 or age > 900:
                quality = "stale"
                gaps.append("Chain source observation is stale or has an invalid future time")
        if raw.get("stale") or (finite(raw.get("cache_age_s")) and raw["cache_age_s"] > 900):
            quality = "stale"
            gaps.append("The cached chain is out of date")
        body = dict(
            ticker=ticker,
            price_only=price_only,
            horizon=horizon,
            window=window,
            source_time=source_time,
            contracts=contracts,
            spot=raw.get("spot"),
            provenance={key: raw.get(key) for key in (
                "source", "data_source", "event_time", "fetched_at", "spot_source",
                "spot_event_time", "spot_fetched_at", "stale", "cache_age_s",
            )},
            dealer=dealer,
            display_selection={
                key: (screen or {}).get(key)
                for key in (
                    "ticker",
                    "page",
                    "mapQuery",
                    "mapVersion",
                    "mapStrikes",
                    "mapExpiries",
                    "selectedStrike",
                    "selectedExpiry",
                    "metric",
                )
            },
            alerts=alerts[:200],
            daily_bars=daily_bars,
        )
        # Sources may contain datetime values; convert timestamps explicitly at seam.
        digest_body = canonical(body)
        snapshot_id = hashlib.sha256(digest_body.encode()).hexdigest()
        facts = []

        def add(metric, value, unit, **kw):
            f = fact(
                metric,
                value,
                unit,
                ticker=ticker,
                source=str(raw.get("source") or raw.get("data_source") or "cached chain"),
                snapshot_id=snapshot_id,
                event_time=source_time,
                received_at=raw.get("fetched_at"),
                horizon=horizon,
                status=quality,
                **kw,
            )
            facts.append(f)
            return f

        spot = raw.get("spot")
        if finite(spot) and spot > 0:
            facts.append(fact("Underlying price", spot, "USD", ticker=ticker,
                              snapshot_id=snapshot_id, horizon=horizon,
                              **spot_provenance(raw, now)))
        if not price_only:
            add("Available contracts", len(contracts), "contracts")
            add("Available expiry dates", sorted({str(contract["expiry"]) for contract in contracts}), "dates")
        valid = [
            c
            for c in contracts
            if not price_only
            and finite(c.get("gamma"))
            and c["gamma"] >= 0
            and finite(c.get("open_interest", c.get("oi")))
            and c.get("open_interest", c.get("oi")) >= 0
            and finite(c.get("strike"))
            and c["strike"] > 0
            and str(c.get("type", "")).upper() in {"C", "P", "CALL", "PUT"}
        ]
        if valid and finite(spot) and spot > 0:
            if len(valid) != len(contracts):
                gaps.append("Exposure excludes contracts with missing inputs")
                quality = "degraded"
            profile = _gex_per_strike(spot, valid)
            if len(profile) <= 512:
                add("Gamma exposure strikes", sorted(profile), "USD")
                add("Estimated gamma exposure", [profile[k] for k in sorted(profile)], "USD per 1% move")
                add("Total estimated gamma exposure", sum(profile.values()), "USD per 1% move")
            else:
                gaps.append("Exposure series exceeds supported size")
            flips = calc_flip_zones(spot, valid)
            levels = [v.get("price", v.get("level")) for v in flips["flip_zones"]]
            levels = [v for v in levels if finite(v)]
            if levels:
                add("Estimated flip levels", levels, "USD")
        elif not price_only:
            gaps.append("Exposure inputs are unavailable")
        if not price_only:
            context = dict(ticker=ticker, snapshot_id=snapshot_id, horizon=horizon, now=now)
            extra, missing = structure_facts(contracts, facts, **context)
            facts.extend(extra)
            gaps.extend(missing)
            extra, missing = volatility_facts(contracts, facts, daily_bars, **context)
            facts.extend(extra)
            gaps.extend(missing)
        flow = []
        flow_times = []
        for alert in alerts[:200]:
            observed = instant(alert.get("asof_ts"))
            if not observed or not 0 <= (now - datetime.fromisoformat(observed)).total_seconds() <= 900:
                continue
            if window["start"] and not window["start"] <= str(alert.get("expiry") or "") <= window["end"]:
                continue
            bias = str(alert.get("bias") or alert.get("direction") or "").lower()
            conviction = alert.get("conviction")
            if bias in {"bullish", "bearish"} and finite(conviction) and 0 <= conviction <= 100:
                flow.append((1 if bias == "bullish" else -1) * conviction / 100)
                flow_times.append(observed)
        flow_status = "unavailable"
        if flow:
            coherent = (
                datetime.fromisoformat(max(flow_times)) - datetime.fromisoformat(min(flow_times))
            ).total_seconds() <= 120
            flow_status = "ok" if coherent else "degraded"
            facts.append(
                fact(
                    "Signed alert reading",
                    sum(flow) / len(flow),
                    "signed agreement",
                    ticker=ticker,
                    source="stored alerts",
                    snapshot_id=snapshot_id,
                    event_time=min(flow_times),
                    horizon=horizon,
                    status=flow_status,
                    reason=None if coherent else "Combines recent alerts with different observation times",
                )
            )
        elif not price_only:
            gaps.append("No eligible fresh directional alerts" if alerts_status == "ok" else "Flow reading unavailable")
        if source_time is None:
            gaps.append("Chain observation time is unknown")
        agreement = score({"flow": sum(flow) / len(flow) if flow else None, "inputs_status": {"flow": flow_status}})
        if agreement["total"] is not None:
            flow_fact = next(f for f in facts if f["metric"] == "Signed alert reading")
            facts.append(
                fact(
                    "Weighted directional agreement",
                    agreement["total"],
                    "agreement points, not probability",
                    ticker=ticker,
                    source="fixed research weights",
                    snapshot_id=snapshot_id,
                    event_time=flow_fact["event_time"],
                    horizon=horizon,
                    status="degraded",
                    reason="Missing dimensions prevent a directional conclusion",
                    version=agreement["weights_version"],
                    parents=[flow_fact["id"]],
                )
            )
        map_facts, map_gaps = ([], []) if price_only else display_facts(dealer, screen or {}, ticker, now)
        facts.extend(map_facts)
        gaps.extend(map_gaps)
        return dict(
            snapshot_id=snapshot_id,
            ticker=ticker,
            horizon=horizon,
            window=window,
            facts=facts,
            gaps=gaps,
            alerts_status=alerts_status,
            flow=flow,
            observed_at=source_time,
            captured_at=now.isoformat(),
            anchor_kind="close" if any(
                f["metric"] == "Underlying price" and f["status"] == "ok"
                and f["event_time"] == instant(window.get("session_close"))
                for f in facts
            ) else "observation",
            coverage=len(contracts),
            agreement=agreement,
            coverage_id=hashlib.sha256(
                canonical(
                    sorted((str(c.get("expiry")), str(c.get("strike")), str(c.get("type"))) for c in contracts)
                ).encode()
            ).hexdigest(),
        )
