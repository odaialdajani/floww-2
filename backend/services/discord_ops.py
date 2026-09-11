"""
backend/services/discord_ops.py

Discord operations for Tidehunter Pro: institutional-alert webhook posts
plus the command layer for the optional gateway bot (backend/discord_bot.py).

Security model (autoRSA-style, stricter):
- Alerts-out needs only DISCORD_WEBHOOK_URL ( Hels webhook, no privileged intents).
- Trading commands (!buy/!sell/!approve) execute ONLY for Discord user IDs
  in DISCORD_ALLOWED_USER_IDS. Empty allowlist = trading commands denied for
  everyone; read-only commands (!holdings/!orders/!alerts/!help) still work.
- Venue is ALWAYS Alpaca paper (paper-api.alpaca.markets is hardcoded in
  alpaca_client) — there is no live-trading code path to misconfigure.
- Secrets via env only; status endpoints report booleans, never values.

Alert gating (env, read at call time so tests can override):
- DISCORD_WEBHOOK_URL (required to post; unset = silent no-op)
- DISCORD_MIN_TIER (default GOLD)
- DISCORD_RULES (default OICONF,WHALE,SCORE,PRIME — comma list)
"""
from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_TIER_RANK = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}

_TIER_COLOR = {"GOLD": 0xE8C96A, "SILVER": 0x9AA4B2, "BRONZE": 0xCD7F32}

# Render-required fields. An alert missing any of these must NEVER reach
# Discord as a "— / —" embed (Sep-2026 incident: gutted WHALE posts).
# Dropped alerts are logged with their key + missing list (the log line IS
# the dead letter) and counted in DROPPED_EMPTY for /api/discord/status.
_REQUIRED_POST_FIELDS = ("type", "strike", "exp", "score", "premium", "why")
DROPPED_EMPTY = {"count": 0}


def validate_alert_for_post(alert: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check an alert can render a non-empty embed. Pure.

    Returns (ok, missing). Empty-string type counts as missing; numeric
    fields accept 0 (a real number, not unknown); why must be non-blank.
    """
    if not isinstance(alert, dict):
        return False, ["not-a-dict"]
    missing: list[str] = []
    if not alert.get("type"):
        missing.append("type")
    for k in ("strike", "exp", "score", "premium"):
        if alert.get(k) is None:
            missing.append(k)
    if not str(alert.get("why") or "").strip():
        missing.append("why")
    return (not missing), missing


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def webhook_url() -> str:
    return _env("DISCORD_WEBHOOK_URL", "").strip()


def min_tier() -> str:
    return _env("DISCORD_MIN_TIER", "GOLD").strip().upper() or "GOLD"


def watched_rules() -> set[str]:
    raw = _env("DISCORD_RULES", "OICONF,WHALE,SCORE,PRIME")
    return {r.strip().upper() for r in raw.split(",") if r.strip()}


def allowed_user_ids() -> set[str]:
    raw = _env("DISCORD_ALLOWED_USER_IDS", "")
    return {u.strip() for u in raw.split(",") if u.strip()}


def is_trading_allowed(user_id: str | int | None) -> bool:
    """Trading commands require a non-empty allowlist containing the user."""
    if user_id is None:
        return False
    allow = allowed_user_ids()
    return bool(allow) and str(user_id) in allow


def should_notify(alert: dict[str, Any]) -> bool:
    """Tier + rule gate for webhook posts. Pure."""
    try:
        tier = str(alert.get("tier", "BRONZE")).upper()
        rule = str(alert.get("rule", "")).upper()
    except Exception:
        return False
    if rule not in watched_rules():
        return False
    return _TIER_RANK.get(tier, 2) <= _TIER_RANK.get(min_tier(), 0)


def _fmt_money(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    a = abs(n)
    if a >= 1e9:
        return f"${n / 1e9:.2f}B"
    if a >= 1e6:
        return f"${n / 1e6:.1f}M"
    if a >= 1e3:
        return f"${n / 1e3:.0f}k"
    return f"${n:.0f}"


def format_alert_message(alert: dict[str, Any]) -> dict[str, Any]:
    """Build a Discord webhook payload (content + one rich embed). Pure."""
    tier = str(alert.get("tier", "BRONZE")).upper()
    rule = str(alert.get("rule", ""))
    under = alert.get("under", "?")
    typ = str(alert.get("type", "")).upper()
    strike = alert.get("strike", "?")
    exp = alert.get("exp", "?")
    bias = alert.get("bias") or "—"
    side = alert.get("side") or "—"
    score = alert.get("score", "—")
    premium = _fmt_money(alert.get("premium"))
    vol_oi = alert.get("vol_oi")
    vol_oi_s = f"{vol_oi:.1f}×" if isinstance(vol_oi, (int, float)) else "—"
    dte = alert.get("dte", "?")
    why = str(alert.get("why", ""))[:300]
    kl = alert.get("key_levels") or {}
    levels = ""
    if kl.get("entry") is not None:
        levels = (f"Entry {kl.get('entry')} · Invalidation {kl.get('invalidation')} "
                  f"· Target {kl.get('target')}")
    key = alert.get("key", "")
    title = f"{tier} {rule} — {under} {typ} {strike} {exp}"
    return {
        "content": f"institutional alert: **{under}** {rule} ({tier})",
        "embeds": [{
            "title": title[:256],
            "color": _TIER_COLOR.get(tier, 0x9AA4B2),
            "fields": [
                {"name": "Bias / Side", "value": f"{bias} / {side}", "inline": True},
                {"name": "Score", "value": str(score), "inline": True},
                {"name": "Premium", "value": premium, "inline": True},
                {"name": "Vol/OI", "value": vol_oi_s, "inline": True},
                {"name": "DTE", "value": str(dte), "inline": True},
                {"name": "Conviction", "value": str(alert.get("conviction", "—")), "inline": True},
                {"name": "Why", "value": why or "—", "inline": False},
                {"name": "Levels", "value": levels or "—", "inline": False},
            ],
            "footer": {"text": f"Reply !approve {key} [qty] to paper-trade this (allowlisted only)"[:2048]},
        }],
    }


async def post_alerts(alerts: list[dict[str, Any]]) -> int:
    """Post qualifying alerts to the webhook. Returns count posted. Never raises.

    Scaling discipline (Discord allows ~30 webhook POSTs/min/channel; a hot
    sweep fires 100+ alerts): 3 or fewer qualifying alerts post as rich
    single embeds (with !approve keys); more than that posts compact
    digests (≤10 embeds/message, ≤3 messages/sweep). Either way every kept
    alert keeps its approve key — batching never eats tradability.
    """
    url = webhook_url()
    if not url:
        return 0
    try:
        import httpx

        qualifying = []
        for a in alerts or []:
            if not should_notify(a):
                continue
            ok, missing = validate_alert_for_post(a)
            if not ok:
                DROPPED_EMPTY["count"] += 1
                logger.warning("discord dropped gutted alert %s (missing %s): %s",
                               a.get("key"), ",".join(missing), a)
                continue
            qualifying.append(a)
        if len(qualifying) <= 3:
            payloads = [format_alert_message(a) for a in qualifying]
        else:
            payloads = build_digest_messages(qualifying)
        posted = 0
        async with httpx.AsyncClient(timeout=10.0) as client:
            for payload in payloads:
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code in (200, 201, 204):
                        posted += 1
                    else:
                        logger.warning("discord webhook HTTP %s", resp.status_code)
                except Exception as e:
                    logger.warning("discord webhook post failed: %s", e)
    except Exception as e:
        logger.warning("discord webhook unavailable: %s", e)
    return posted


def build_digest_messages(alerts: list[dict[str, Any]], max_embeds: int = 10,
                          max_msgs: int = 3) -> list[dict[str, Any]]:
    """Compact multi-alert digest payloads (pure). Ranked by conviction desc.

    Each row keeps rule/tier/under/bias/score/premium/approve-key so the
    digest stays actionable. Overflow collapses into a "+N more" footer row
    (counted honestly, never silently dropped from the tally).
    """
    def _conv(a: dict[str, Any]) -> float:
        # Explicit None checks — `or`-chaining would promote conviction 0
        # above everything via the score fallback. Zero is a measurement.
        for k in ("conviction", "score"):
            try:
                v = a.get(k)
                if v is not None:
                    return float(v)
            except (TypeError, ValueError):
                continue
        return 0.0

    ranked = sorted(alerts or [], key=_conv, reverse=True)
    embeds: list[dict[str, Any]] = []
    for a in ranked:
        ok, missing = validate_alert_for_post(a)
        if not ok:
            DROPPED_EMPTY["count"] += 1
            logger.warning("discord digest dropped gutted alert %s (missing %s)",
                           a.get("key"), ",".join(missing))
            continue
        tier = str(a.get("tier", "BRONZE")).upper()
        under = a.get("under", "?")
        rule = a.get("rule", "")
        bias = a.get("bias") or "—"
        score = a.get("score", "—")
        premium = _fmt_money(a.get("premium"))
        key = a.get("key", "")
        embeds.append({
            "title": f"{tier} {rule} — {under} {bias}",
            "color": _TIER_COLOR.get(tier, 0x9AA4B2),
            "description": (f"score {score} · {premium} · `{key}`"[:900]),
        })
    total = len(embeds)
    shown = embeds[: max_msgs * max_embeds]
    messages: list[dict[str, Any]] = []
    for i in range(0, len(shown), max_embeds):
        messages.append({
            "content": f"⚡ institutional digest: **{total} alerts** (top by conviction)",
            "embeds": shown[i:i + max_embeds],
        })
    if total > len(shown) and messages:
        # Overflow rides in the last message's content (embeds cap at 10) —
        # counted honestly, never silently dropped from the tally.
        messages[-1]["content"] += f" · +{total - len(shown)} more in the scanner"
    return messages


async def post_image(png: bytes | None, filename: str, content: str = "") -> bool:
    """Post a PNG file to the webhook (multipart). False when unset/fails. Never raises."""
    url = webhook_url()
    if not url or not png:
        return False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                data={"content": content[:1900]},
                files={"file": (filename, png, "image/png")},
            )
            if resp.status_code in (200, 201, 204):
                return True
            logger.warning("discord image post HTTP %s", resp.status_code)
            return False
    except Exception as e:
        logger.warning("discord image post failed: %s", e)
        return False


def parse_command(text: str) -> dict[str, Any] | None:
    """Parse `!cmd args` bot commands. Pure. Returns None when not a command."""
    if not text or not isinstance(text, str):
        return None
    parts = text.strip().split()
    if not parts or not parts[0].startswith("!"):
        return None
    cmd = parts[0][1:].lower()
    args = parts[1:]
    if cmd in ("buy", "sell") and len(args) >= 2:
        try:
            qty = int(args[0])
        except (TypeError, ValueError):
            return None
        out: dict[str, Any] = {"cmd": cmd, "qty": qty, "symbol": args[1].upper()}
        if len(args) >= 4 and args[2].lower() == "limit":
            try:
                out["limit_price"] = float(args[3])
                out["order_type"] = "limit"
            except (TypeError, ValueError):
                return None
        else:
            out["order_type"] = "market"
        return out
    if cmd == "approve" and len(args) >= 1:
        out = {"cmd": "approve", "key": args[0]}
        if len(args) >= 2:
            try:
                out["qty"] = int(args[1])
            except (TypeError, ValueError):
                return None
        return out
    if cmd in ("holdings", "positions"):
        return {"cmd": "holdings"}
    if cmd == "orders":
        return {"cmd": "orders"}
    if cmd == "alerts":
        try:
            n = int(args[0]) if args else 5
        except (TypeError, ValueError):
            return None
        return {"cmd": "alerts", "n": max(1, min(n, 10))}
    if cmd in ("help", "h"):
        return {"cmd": "help"}
    return None


HELP_TEXT = (
    "**SOLSTICE — dealer-positioning desk** (gamma/vanna exposure)\n"
    "`!heatmap <TICKER>` — GEX ladder picture (walls, flip, King Node)\n"
    "`!vanna <TICKER>` — VEX (vomma exposure) picture\n"
    "`!walls <TICKER>` — call/put walls, flip, regime readout\n"
    "Paper trading (Alpaca paper ONLY):\n"
    "`!buy <qty> <SYM> [limit <px>]` · `!sell <qty> <SYM>`\n"
    "`!bracket <buy|sell> <qty> <SYM> <tp%> <sl%>` — entry + TP/SL legs\n"
    "`!approve <alert-key> [qty]` — trade a posted alert (journaled)\n"
    "`!close <SYM>` · `!holdings` · `!orders` · `!pnl` · `!risk`\n"
    "`!journal [n]` · `!alerts [n]` · `!help [solstice|trading|portfolio]`\n"
    "Trading commands require allowlist membership."
)


def fetch_recent_alerts(engine, limit: int = 10, min_tier: str = "GOLD") -> list[dict]:
    """Recent alerts for `!alerts` / `!approve` resolution. Never raises."""
    try:
        from services.flow_alerts import read_alert_feed

        return read_alert_feed(engine, days=2, min_tier=min_tier)[: max(1, int(limit))]
    except Exception as e:
        logger.warning("discord recent-alerts unavailable: %s", e)
        return []


async def execute_approve(alert_key: str, qty: int | None, engine, router) -> dict[str, Any]:
    """Execute an alert-derived paper trade. Returns a result dict (never raises).

    Direction from alert bias (BULLISH→buy, BEARISH→sell); size defaults to
    1 share; paper venue only.
    """
    try:
        rows = fetch_recent_alerts(engine, limit=50)
        if rows is None:
            # Feed itself failed (vs answered-empty): say unavailable,
            # never "alert not found". Forward-compatible with the
            # alerts-honesty contract ([] still means zero rows).
            return {"status": "error",
                    "reason": "alert feed unavailable — try !alerts later",
                    "alert": alert_key}
        alert = next((a for a in rows if a.get("key") == alert_key), None)
        if alert is None:
            return {"status": "error", "reason": f"alert not found: {alert_key}"}
        bias = str(alert.get("bias") or "").upper()
        if bias not in ("BULLISH", "BEARISH"):
            return {"status": "error", "reason": "alert has no directional bias"}
        side = "buy" if bias == "BULLISH" else "sell"
        symbol = str(alert.get("under", "")).upper()
        if not symbol:
            return {"status": "error", "reason": "alert has no underlying"}
        q = int(qty) if qty else 1
        if q <= 0:
            return {"status": "error", "reason": "qty must be positive"}
        if _approve_already_journaled(alert_key):
            return {"status": "duplicate",
                    "reason": f"already approved: {alert_key}",
                    "alert": alert_key}
        res = await router.submit_order({
            "ticker": symbol, "side": side, "qty": q, "order_type": "market",
            "signal_id": f"discord-approve:{alert_key}:{side}:{q}",
            "timestamp_us": int(time.time() * 1e6),
        }, allow_market=True)
        if res.get("status") == "submitted":
            rec = await _reconcile_fill(router, res)
            _journal_approve_fill(alert, side, q, res, rec)
            return {"status": "submitted", "order": res, "alert": alert_key,
                    "reconciliation": rec}
        return {"status": res.get("status", "error"), "order": res, "alert": alert_key,
                "reconciliation": {"venue_status": "unknown", "reason": "order not submitted"}}
    except TypeError as e:
        # Back-compat: a router stub without the allow_market opt-in.
        if "allow_market" in str(e):
            logger.warning("discord approve router missing allow_market: %s", e)
            return {"status": "error", "reason": "router missing market opt-in"}
        logger.warning("discord approve failed: %s", e)
        return {"status": "error", "reason": str(e)}
    except Exception as e:
        logger.warning("discord approve failed: %s", e)
        return {"status": "error", "reason": str(e)}


def _approve_already_journaled(alert_key: str) -> bool:
    """True when this alert key already has a discord-approve seed.

    Duplicate-approve guard (G3.3 idempotency): the router cache keys on
    (signal_id, timestamp), so two taps mint different client_order_ids —
    the journal is the cross-call dedup record. Fail-open: any read error
    means "not seen", the trade proceeds.
    """
    try:
        from services.journal_store import get_engine, init_journal_tables, read_trades

        engine = get_engine()
        init_journal_tables(engine)
        for t in read_trades(engine, days=30):
            if t.get("source") == "discord-approve" and alert_key in str(t.get("notes", "")):
                return True
        return False
    except Exception:
        return False


async def _reconcile_fill(router, res: dict) -> dict:
    """One-shot venue refetch after submit (fail-open, never raises).

    Returns {"venue_status", "filled_avg_price", "filled_qty", "reason"}.
    Unknown when the broker lacks the read path or the refetch fails —
    the seed stays submission-language in that case.
    """
    try:
        raw_broker = res.get("broker")
        broker = raw_broker if isinstance(raw_broker, dict) else {}
        venue_id = str(broker.get("id", "") or "")
        fetch = getattr(router, "fetch_venue_order", None)
        if not venue_id or not callable(fetch):
            return {"venue_status": "unknown",
                    "reason": "no venue read available at submit time"}
        order = await fetch(venue_id)  # pyright: ignore
        if not isinstance(order, dict):
            return {"venue_status": "unknown",
                    "reason": f"venue refetch empty for {venue_id}"}
        return {"venue_status": str(order.get("status", "unknown")),
                "filled_avg_price": order.get("filled_avg_price", ""),
                "filled_qty": order.get("filled_qty", ""),
                "reason": ""}
    except Exception as e:
        return {"venue_status": "unknown", "reason": f"refetch failed: {e}"}


def _journal_approve_fill(alert: dict[str, Any], side: str, qty: int, res: dict,
                          rec: dict | None = None) -> None:
    """Record an executed approve trade in the journal (fail-open).

    Approve fills are EQUITY (Alpaca place_stock_order on the underlying),
    so the seed is equity-shaped (type=equity, no strike/expiry) — never
    mislabeled as an option contract. The journal is the position memory:
    lifecycle tracking follows it to exit. Never raises into the trade path.
    """
    try:
        from services.journal_store import get_engine, init_journal_tables, save_seeds

        broker_raw = res.get("broker")
        broker_map = broker_raw if isinstance(broker_raw, dict) else {}
        broker_id = res.get("client_order_id") or broker_map.get("id", "")
        broker_status = broker_map.get("status", "")
        rec = rec or {}
        venue_status = str(rec.get("venue_status", "unknown") or "unknown")
        fill_bits = ""
        if venue_status not in ("unknown",):
            px = rec.get("filled_avg_price", "") or ""
            fq = rec.get("filled_qty", "") or ""
            fill_bits = f" | venue reports {venue_status}" + (f" {fq} @ {px}" if fq or px else "")
        # Equity legs have no strike, but strike is PK-NOT-NULL in
        # flow_journal_trades: store the underlying reference price (or 0.0),
        # labeled as such in notes. Uniqueness comes from the per-second
        # entry_date, so same-day re-trades never silently vanish.
        try:
            ref_px = float(alert.get("under_price") or 0)
        except (TypeError, ValueError):
            ref_px = 0.0
        seed = {
            "ticker": str(alert.get("under", "")).upper(),
            "type": "equity",
            "action": side,
            "strike": ref_px,
            "expiry": "",
            "quantity": str(qty),
            "entry_price": None,
            "exit_price": "",
            # Full timestamp (not date-only): equity re-trades the same day
            # must not PK-collide and silently vanish from position memory.
            "entry_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "exit_date": "",
            "notes": (f"Discord approve {side} {qty} shares from {alert.get('rule')} "
                      f"{alert.get('tier')} alert ({alert.get('key')}) | "
                      f"Alpaca paper ({broker_id}, broker status '{broker_status or 'submitted'}' — "
                      f"submission, not a confirmed fill; reconcile via get_order){fill_bits} | "
                      f"ref px {ref_px} (equity leg, "
                      f"not a strike) | {alert.get('why', '')}"[:500]),
            "gex_regime": "",
            "setup": f"{str(alert.get('rule') or '').lower()} approve",
            "tags": "discord,approve,equity",
            "source": "discord-approve",
            "key_levels": alert.get("key_levels"),
        }
        engine = get_engine()
        init_journal_tables(engine)
        save_seeds(engine, [seed])
    except Exception as e:
        logger.warning("discord approve journaling failed (non-fatal): %s", e)
