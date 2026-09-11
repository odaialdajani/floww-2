"""Deterministic explanations from saved evidence; no model-authored numbers."""

import re

from services.agent.contracts import finite


def request_limit(question):
    text = question.lower()
    limits = []
    if re.search(r"\b(?:earnings|dividend|news|economic release)\b", text):
        limits.append(
            "I do not have verified company or event evidence, so I cannot give an event date or news conclusion."
        )
    if re.search(r"\b(?:adjusted|deliverable|settlement|exercise|assignment)\b", text):
        limits.append(
            "Verified contract deliverable and settlement terms are unavailable; I cannot treat this as a standard option."
        )
    if re.search(r"\b(?:probability|chance|odds|guaranteed?|certain)\b", text):
        limits.append("A calibrated target probability is unavailable. These readings cannot guarantee a profit.")
    if re.search(r"\b(?:paper account|paper trade|paper order)\b", text):
        limits.append(
            "No paper order or fill was created. The approved paper account is not available through research."
        )
    elif re.search(r"\b(?:send|place|execute|submit)\b.{0,35}\border\b|^\s*(?:buy|sell)\b", text):
        limits.append("No order was sent or staged. This panel provides research only.")
    if re.search(r"\b(?:spx|ndx|rut)\b", text) and re.search(r"\b(?:option|contract|etf|standard)\b", text):
        limits.append(
            "Index contract terms are not verified here; standard share-based option assumptions cannot establish their value or risk."
        )
    return " ".join(limits)


def explain_snapshot(snapshot):
    facts = {item["metric"]: item for item in snapshot["facts"]}
    explanations = []
    window = snapshot.get("window", {})
    if window.get("start") and window.get("end"):
        explanations.append(f"Requested expiry scope: {window['start']} through {window['end']}.")
    expiry = facts.get("Available expiry dates")
    if expiry:
        explanations.append("Available expiries: " + (", ".join(expiry["value"]) or "none") + ".")
    spot, flips = facts.get("Underlying price"), facts.get("Estimated flip levels")
    if spot and flips and spot["status"] == flips["status"] == "ok" and spot["event_time"] == flips["event_time"]:
        levels = [value for value in flips["value"] if finite(value)]
        if finite(spot["value"]) and levels:
            nearest = min(levels, key=lambda value: abs(value - spot["value"]))
            relation = "above" if spot["value"] > nearest else "below" if spot["value"] < nearest else "at"
            explanations.append(f"The saved price is {relation} the nearest estimated flip of {nearest:,.4g} USD.")
    gamma = facts.get("Total estimated gamma exposure")
    if gamma and gamma["status"] == "ok" and finite(gamma["value"]):
        if gamma["value"] < 0:
            explanations.append(
                "The negative-gamma estimate describes a setting where dealer hedging can amplify moves; it does not establish their direction or verify actual dealer positions."
            )
        elif gamma["value"] > 0:
            explanations.append(
                "The positive-gamma estimate describes a setting where dealer hedging can dampen moves; it does not establish their direction or verify actual dealer positions."
            )
        else:
            explanations.append(
                "The supplied contracts have zero net estimated gamma; that does not establish a neutral price outlook."
            )
    flow = snapshot.get("flow", [])
    if any(value > 0 for value in flow) and any(value < 0 for value in flow):
        explanations.append(
            "The recent directional alerts disagree. A balanced net reading does not mean there was no activity."
        )
    return " ".join(explanations)
