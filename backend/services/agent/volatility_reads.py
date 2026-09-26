"""Pure, evidence-gated volatility reads. No fetches and no guessed cutoffs.

Daily bars are an optional copy-only input envelope: ticker, interval='1d',
source, event_time, price_basis, complete=True, and bars [{date, close}].
Dates must be consecutive completed XNYS sessions. No OHLC fallback is used.
"""

from __future__ import annotations

from datetime import date, datetime

from services.agent.access.horizon import ET, _calendar, fractional_years, required_close
from services.agent.contracts import fact, finite, instant
from services.agent.structure_reads import derived_fact, exact_expiry, iv_input_fact
from services.gex_core import calc_implied_move
from services.realized_volatility import compute_realized_volatility


def _implied(contracts, existing, context, now):
    by_name = {f["metric"]: f for f in existing}
    spot = by_name.get("Underlying price")
    coverage = by_name.get("Available contracts")
    positive_iv = sum(finite(c.get("iv")) and c["iv"] > 0 for c in contracts)
    future_expiries = sum((expiry := exact_expiry(c)) is not None and expiry > now for c in contracts)
    price_input = (f"saved underlying price is present ({spot.get('status', 'unknown')})"
                   if spot and finite(spot.get("value")) and spot["value"] > 0
                   else "usable saved underlying price is missing")
    chain_time = instant((coverage or {}).get("event_time"))
    timing = f"chain observation time is {chain_time}" if chain_time else "chain observation time is unknown"
    missing = ("Implied move is unavailable: " + price_input
               + f"; positive IV on {positive_iv} of {len(contracts)} saved contracts"
               + f"; usable explicit future expiry time on {future_expiries} of {len(contracts)}; {timing}. "
               + "These are separate input checks, not proof of a matched pair. A current verified price and "
               + "one same-expiry at-the-money call and put need positive IV, aligned verified source times "
               + "and an explicit product expiry instant. A calendar expiry date alone is insufficient.")
    if not spot or not coverage or any(p.get("status") != "ok" for p in (spot, coverage)):
        return [], [missing]
    if any(str(p.get("source") or "unknown") in {"unknown", "cached chain"} for p in (spot, coverage)):
        return [], [missing]
    if not finite(spot["value"]) or spot["value"] <= 0 or not contracts:
        return [], [missing]
    times = [instant(p.get("event_time")) for p in (spot, coverage)]
    if any(t is None or not 0 <= (now - datetime.fromisoformat(t)).total_seconds() <= 900 for t in times):
        return [], [missing]
    if abs((datetime.fromisoformat(times[0]) - datetime.fromisoformat(times[1])).total_seconds()) > 120:
        return [], ["Implied move is unavailable: price and IV observations are not contemporaneous"]
    # Never jump past the requested nearest expiry or ATM strike to find data.
    expiry_date = min(str(c.get("expiry")) for c in contracts)
    scope = [c for c in contracts if str(c.get("expiry")) == expiry_date]
    strikes = [c["strike"] for c in scope if finite(c.get("strike")) and c["strike"] > 0]
    if not strikes:
        return [], [missing]
    atm = min(strikes, key=lambda strike: (abs(strike - spot["value"]), strike))
    pair = []
    for kinds, kind in (({"C", "CALL"}, "call"), ({"P", "PUT"}, "put")):
        matching = [c for c in scope if c.get("strike") == atm and str(c.get("type", "")).upper() in kinds]
        if len(matching) != 1:
            return [], ["Implied move is unavailable: one unambiguous same-expiry ATM call and put are required"]
        c = matching[0]
        expiry = exact_expiry(c)
        iv_time = instant(c.get("iv_event_time", coverage["event_time"]))
        if (not finite(c.get("iv")) or c["iv"] <= 0 or expiry is None or expiry <= now
                or iv_time is None or not 0 <= (now - datetime.fromisoformat(iv_time)).total_seconds() <= 900
                or abs((datetime.fromisoformat(iv_time) - datetime.fromisoformat(times[1])).total_seconds()) > 120):
            return [], [missing]
        pair.append({**c, "type": kind, "T": fractional_years(expiry, now=now), "_iv_observation": iv_time})
    if instant(pair[0]["expiry_instant"]) != instant(pair[1]["expiry_instant"]):
        return [], ["Implied move is unavailable: call and put expiry instants disagree"]
    all_times = [*times, *(c["_iv_observation"] for c in pair)]
    if (datetime.fromisoformat(max(all_times)) - datetime.fromisoformat(min(all_times))).total_seconds() > 120:
        return [], ["Implied move is unavailable: price and IV observations are not contemporaneous"]
    try:
        result = calc_implied_move(spot["value"], pair)
    except (ArithmeticError, ValueError, TypeError):
        result = None
    if not result or not all(finite(v) for v in result.values()):
        return [], ["Implied move calculator did not return usable values"]
    parents = [spot, coverage]
    reason = "Existing 0.8 * spot * mean ATM IV * sqrt(remaining years) estimate; not a quoted straddle or guaranteed range"
    facts = [iv_input_fact("At-the-money implied volatility", sum(c["iv"] for c in pair) / 2,
                           [c["_iv_observation"] for c in pair], coverage, context, now)]
    for metric, value, unit in (
        ("Implied move expiry instant", instant(pair[0]["expiry_instant"]), "UTC instant"),
        ("Implied move remaining years", pair[0]["T"], "365-day years"),
    ):
        facts.append(derived_fact(metric, value, unit, parents, context, reason=reason))
    for metric, key, unit in (("Implied move estimate", "implied_move_dollars", "USD"),
                              ("Implied move percent", "implied_move_pct", "percent"),
                              ("Implied move lower bound", "lower_range", "USD"),
                              ("Implied move upper bound", "upper_range", "USD")):
        facts.append(derived_fact(metric, result[key], unit, [*parents, *facts[:3]], context, reason=reason))
    return facts, []


def _realized(envelope, context, now):
    missing = "Realized volatility is unavailable: coherent completed daily bars with source and price basis are required"
    if not isinstance(envelope, dict):
        return [], [missing]
    bars = envelope.get("bars")
    source = envelope.get("source")
    if (envelope.get("ticker") != context["ticker"] or envelope.get("interval") != "1d"
            or envelope.get("complete") is not True
            or envelope.get("price_basis") not in {"unadjusted", "split_adjusted", "adjusted"}
            or not isinstance(source, str) or not source.strip()
            or not isinstance(bars, list) or not 3 <= len(bars) <= 512):
        return [], [missing]
    dates, closes = [], []
    for bar in bars:
        if not isinstance(bar, dict) or not finite(bar.get("close")) or bar["close"] <= 0:
            return [], [missing]
        if bar.get("complete", True) is not True:
            return [], [missing]
        if bar.get("ticker", context["ticker"]) != context["ticker"] or bar.get("source", source) != source:
            return [], ["Realized volatility is unavailable: bar sources or tickers are mixed"]
        if bar.get("price_basis", envelope["price_basis"]) != envelope["price_basis"]:
            return [], ["Realized volatility is unavailable: bar price bases are mixed"]
        try:
            dates.append(date.fromisoformat(str(bar.get("date"))).isoformat())
        except ValueError:
            return [], [missing]
        closes.append(bar["close"])
    if dates != sorted(set(dates)):
        return [], ["Realized volatility is unavailable: dates are duplicated or out of order"]
    try:
        cal = _calendar()
        expected = [d.date().isoformat() for d in cal.sessions_in_range(dates[0], dates[-1])]
        if dates != expected or cal.session_close(dates[-1]).to_pydatetime() > now:
            return [], ["Realized volatility is unavailable: daily history has missing or incomplete sessions"]
    except (ValueError, KeyError):
        return [], [missing]
    observed = instant(envelope.get("event_time"))
    status = envelope.get("status", "ok")
    if status not in {"ok", "degraded", "stale"}:
        return [], [missing]
    last_completed = datetime.fromisoformat(required_close(now)).astimezone(ET).date().isoformat()
    if dates[-1] < last_completed:
        status = "stale"
    if observed and (datetime.fromisoformat(observed) > now
                     or datetime.fromisoformat(observed) < cal.session_close(dates[-1]).to_pydatetime()):
        return [], ["Realized volatility is unavailable: source time cannot establish completed daily history"]
    try:
        result = compute_realized_volatility([{"date": d, "close": c} for d, c in zip(dates, closes, strict=True)],
                                             estimator="close_to_close", annualisation_factor=252)
    except (ArithmeticError, ValueError, TypeError):
        result = {}
    value = result.get("volatility")
    if not finite(value) or value < 0 or result.get("warnings"):
        return [], ["Realized volatility calculator did not return a complete usable estimate"]
    inputs = [fact(metric, values, unit, **context, source=source, event_time=observed,
                   received_at=envelope.get("received_at"), status=status,
                   reason=f"Completed daily bars; {envelope['price_basis']} prices")
              for metric, values, unit in (("Realized volatility observation dates", dates, "dates"),
                                           ("Realized volatility close prices", closes, "USD"))]
    output = derived_fact("Realized daily close volatility", value, "annualized fraction", inputs, context,
                          reason="Sample standard deviation of daily log returns times sqrt(252); historical window only")
    return [*inputs, output], []


def volatility_facts(contracts, existing, daily_bars, *, ticker, snapshot_id, horizon, now):
    context = dict(ticker=ticker, snapshot_id=snapshot_id, horizon=horizon)
    implied, implied_gaps = _implied(contracts, existing, context, now)
    realized, realized_gaps = _realized(daily_bars, context, now)
    return [*implied, *realized], [*implied_gaps, *realized_gaps]
