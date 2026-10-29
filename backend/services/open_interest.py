"""Unsigned counts from loaded contracts; never modeled exposure."""
import math
from datetime import date


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def build_open_interest(contracts):
    cells, strikes, sources, dates = {}, set(), set(), set()
    excluded = 0
    for row in contracts or []:
        if not isinstance(row, dict):
            excluded += 1
            continue
        strike, expiry = _number(row.get("strike")), row.get("expiry")
        side = {"call": "call", "put": "put", "c": "call", "p": "put"}.get(str(row.get("type", "")).lower())
        try:
            valid_date = isinstance(expiry, str) and date.fromisoformat(expiry).isoformat() == expiry
        except ValueError:
            valid_date = False
        if strike is None or strike <= 0 or not valid_date or side is None:
            excluded += 1
            continue
        key = str(int(strike)) if strike == int(strike) else str(strike)
        strikes.add(strike)
        cell = cells.setdefault(expiry, {}).setdefault(key, {
            "call": None, "put": None, "total": None, "known": 0,
            "missing": 0, "invalid": 0, "quarantined": 0, "seen": [],
        })
        if side in cell["seen"]:
            cell["invalid"] += 1
            cell[side] = None
            continue
        cell["seen"].append(side)
        if row.get("adjusted") or row.get("nonstandard"):
            cell["quarantined"] += 1
            continue
        value = row.get("oi") if "oi" in row else row.get("open_interest")
        number = _number(value)
        if value is None:
            cell["missing"] += 1
        elif number is None or number < 0 or number > 2**53 - 1 or number != int(number):
            cell["invalid"] += 1
        else:
            cell[side] = int(number)
            cell["known"] += 1
        if isinstance(row.get("oi_source"), str):
            sources.add(row["oi_source"])
        if isinstance(row.get("oi_effective_date"), str):
            dates.add(row["oi_effective_date"])
    usable, incomplete = 0, bool(excluded)
    for column in cells.values():
        for cell in column.values():
            del cell["seen"]
            bad = cell["missing"] + cell["invalid"] + cell["quarantined"]
            if not bad and cell["known"]:
                total = sum(cell[s] for s in ("call", "put") if cell[s] is not None)
                if total > 2**53 - 1:
                    cell["invalid"] += 1
                    cell["reason"] = "total_out_of_range"
                    bad += 1
                else:
                    cell["total"] = total
                    usable += 1
            incomplete |= bool(bad)
    return {"version": "oi-counts.v1", "units": "contracts", "signed": False,
            "strikes": sorted(strikes), "expiries": sorted(cells), "cells": cells,
            "status": "partial" if incomplete and cells else ("ok" if usable else "unavailable"),
            "invalid_contracts": excluded, "sources": sorted(sources),
            "oi_effective_dates": sorted(dates), "scope": "loaded contracts only"}
