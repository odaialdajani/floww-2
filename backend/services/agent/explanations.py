"""Evidence-bound explanations the model may select, never invent.

These teach the meaning and limits of supplied readings. They make no new
market prediction and do not turn unknown source quality into current data.
Gamma definition: https://www.optionseducation.org/advancedconcepts/gamma
Option premium inputs: https://www.optionseducation.org/referencelibrary/faq/option-price-behavior
"""

import hashlib
import json
from collections import defaultdict
from datetime import datetime

from services.agent.contracts import finite, instant


def compatible_pair(left, right):
    times = [instant(item.get("event_time")) for item in (left, right)]
    return (all(item.get("status") == "ok" and finite(item.get("value")) for item in (left, right))
            and all(left.get(key) == right.get(key) for key in ("ticker", "horizon", "unit"))
            and all(times)
            and abs((datetime.fromisoformat(times[0]) - datetime.fromisoformat(times[1])).total_seconds()) <= 120)


def explanation_menu(facts):
    groups = defaultdict(list)
    for fact in facts:
        if not isinstance(fact,dict) or not all(isinstance(fact.get(key),str) and fact[key] for key in ("id","ticker","horizon","metric")):
            continue
        groups[(fact["ticker"], fact["horizon"])].append(fact)
    menu = []
    for (ticker, horizon), items in groups.items():
        metrics = {f["metric"]: f for f in items}
        refs = [f["id"] for f in items[:12]]

        def add(kind, text, evidence=None, ticker=ticker, horizon=horizon, refs=refs):
            item = dict(kind=kind, ticker=ticker, horizon=horizon,
                        fact_ids=[f["id"] for f in evidence] if evidence else refs,
                        text=f"{ticker} (scope {horizon}): {text}")
            item["id"] = "ex" + hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()
            menu.append(item)

        add("source_time", "Saving or receiving a reading recently does not prove the market quote is recent. "
            "Only its source observation time establishes when it was observed; unknown times remain unknown.")
        gamma = [f for f in items if "gamma exposure" in f["metric"].lower()]
        if gamma:
            add("gamma_meaning", "Gamma describes how an option's delta changes as the underlying price moves. "
                "The exposure estimate combines that sensitivity with open interest and assumed position signs. "
                "It does not observe actual dealer holdings or predict which way price will move.", gamma[:12])
        coverage = [metrics[m] for m in ("Available contracts","Available expiry dates") if m in metrics]
        if coverage:
            add("coverage_limits", "The contract count and expiry dates describe only the saved coverage. "
                "They do not establish that every listed contract, every expiry, or every market participant is covered.",coverage)
        prices = [f for f in items if f["metric"] in {"Underlying price","Cached map price"}]
        flips = [f for f in items if "flip" in f["metric"].lower()]
        if prices and not flips:
            add("missing_flip", "No usable flip level is supplied, so the saved price cannot be placed above or below a flip. "
                "A price alone cannot establish that comparison.", prices)
        elif prices and flips and not any(compatible_pair(price, flip) for price in prices for flip in flips):
            add("limited_comparison", "No healthy, compatible scalar price-versus-flip pair is supplied for this scope. "
                "The values, coverage or source times cannot establish that comparison. Showing both numbers does not make them a current, compatible pair.",
                (prices+flips)[:12])
        if not any(f.get("status") == "ok" and f.get("event_time") for f in items):
            add("no_current_readings", "None of the supplied readings has both verified source time and healthy quality. "
                "They may describe a saved snapshot, but cannot establish a current market comparison.")
        flow = [f for f in items if f["metric"] == "Signed alert reading"]
        if not flow:
            add("missing_alerts", "No usable directional-alert reading is supplied. That does not mean nobody traded. "
                "A missing, filtered or unreadable alert record cannot establish either market direction or an absence of activity.")
        else:
            add("alert_limits", "The alert reading summarizes selected, derived signals. It is not a complete trade tape "
                "or proof of who bought, sold, or held the options.",flow)
        implied = [f for f in items if "implied" in f["metric"].lower() and f.get("value") is not None]
        realized = [f for f in items if "realized" in f["metric"].lower() and f.get("value") is not None]
        if not implied or not realized:
            absent = "implied and realized volatility estimates" if not implied and not realized else "implied volatility estimates" if not implied else "realized volatility estimates"
            add("missing_volatility", f"The supplied evidence lacks usable {absent}. "
                "Some raw inputs may be present; the listed source gaps explain what remains unverified. "
                "An implied-versus-realized comparison cannot be calculated from price, gamma or alerts alone.")
        if not any(f["metric"] == "Price change since saved observation" for f in items):
            add("missing_change", "No validated price change from an earlier compatible observation is supplied. "
                "A single snapshot cannot establish how much the market changed; matching scope, source and observation times are required.")
        if prices and not any("option" in f["metric"].lower() and any(k in f["metric"].lower() for k in ("bid","ask","quote")) for f in items):
            add("missing_option_quote", "The underlying price is not an option premium. No verified option bid and ask for "
                "the exact contract are supplied, so these facts cannot provide an executable option entry price.",prices)
    return menu[:36]


def select_explanations(ids, facts):
    if not isinstance(ids,list) or len(ids)>4 or any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)):
        raise ValueError("Invalid explanation selection")
    available = {item["id"]:item for item in explanation_menu(facts)}
    if any(i not in available for i in ids):
        raise ValueError("Explanation is not supported by the supplied evidence")
    return [available[i] for i in ids]


def compact_explanation_menu(facts):
    """Lossless wire representation; answer IDs and server validation stay unchanged.

    Several explanations cite exactly the same evidence. Send each ordered
    citation list once, and point to it from every matching menu entry.
    """
    groups = {}
    identities = {}
    entries = []
    for item in explanation_menu(facts):
        refs = tuple(item['fact_ids'])
        if refs not in identities:
            group = f'evidence_{len(groups) + 1}'
            identities[refs] = group
            groups[group] = list(refs)
        entry = {key: value for key, value in item.items() if key != 'fact_ids'}
        entry['evidence_group'] = identities[refs]
        entries.append(entry)
    return {'explanation_menu': entries, 'explanation_evidence': groups}
