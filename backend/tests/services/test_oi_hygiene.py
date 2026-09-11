"""
backend/tests/services/test_oi_hygiene.py

ΔOI hygiene contracts on synthetic chains with known answers:
  - OCC expiry parsing (incl. malformed tails)
  - expiring contracts are flagged for oiChg nulling
  - roll pairs (near expiry bleeding, next expiry swelling) are tagged
  - earnings windows tag within ±4 sessions, honestly unknown otherwise
  - the why-suffix is the shared client/server contract
  - the alert engine consumes tags: rollover OI pops do NOT fire OICONF,
    earnings-tagged OICONF is capped below GOLD
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services import oi_hygiene as oh  # noqa: E402


def _row(under="SPY", typ="call", strike=600, exp="2026-09-04", occ=None, oi=1000):
    if occ is None:
        occ = f"{under}{exp[2:4]}{exp[5:7]}{exp[8:10]}{'C' if typ == 'call' else 'P'}{int(strike * 1000):08d}"
    return {
        "under": under, "type": typ, "strike": strike, "exp": exp,
        "occ": occ,
        "oi": oi, "dte": 2, "ckey": f"{under}|{typ}|{strike:g}|{exp}",
    }


# ── OCC expiry parsing ───────────────────────────────────────────────

def test_occ_expiry_parses_yymmdd_tail():
    assert oh.occ_expiry("SPY260904C00600000") == date(2026, 9, 4)
    assert oh.occ_expiry("tsla251219P00120000") == date(2025, 12, 19)
    assert oh.occ_expiry("AAPL240621C00190000") == date(2024, 6, 21)


def test_occ_expiry_malformed_returns_none():
    assert oh.occ_expiry("") is None
    assert oh.occ_expiry(None) is None
    assert oh.occ_expiry("GARBAGE") is None
    assert oh.occ_expiry("SPY261332C00600000") is None  # month 13


# ── expiring contracts ───────────────────────────────────────────────

def test_expiring_contract_flagged_for_oi_nulling():
    today = date(2026, 9, 2)
    rows = [_row(exp="2026-09-02", oi=500),   # expires today
            _row(exp="2026-09-30", oi=900)]   # live
    prev = {rows[0]["ckey"]: 400, rows[1]["ckey"]: 800}
    tags = oh.oi_hygiene_tags(rows, prev, today=today)
    assert tags[rows[0]["ckey"]]["expiring"] is True
    assert tags[rows[1]["ckey"]]["expiring"] is False


# ── roll pairs ───────────────────────────────────────────────────────

def test_roll_pair_detected():
    today = date(2026, 9, 2)
    near = _row(exp="2026-09-04", occ="SPY260904C00600000", oi=300)   # bled 70%
    nxt = _row(exp="2026-10-02", occ="SPY261002C00600000", oi=1200)   # grew +140%
    prev = {near["ckey"]: 1000, nxt["ckey"]: 500}
    tags = oh.oi_hygiene_tags([near, nxt], prev, today=today)
    assert tags[near["ckey"]]["rollover"] is True
    assert tags[nxt["ckey"]]["rollover"] is True
    assert tags[near["ckey"]]["expiring"] is False  # future expiry: live contract


def test_genuine_new_flow_not_tagged_rollover():
    """Near expiry bled but next expiry ALSO bled → not a roll; and a fresh
    next-expiry pop with a bleeding near leg needs both legs to qualify."""
    today = date(2026, 9, 2)
    near = _row(exp="2026-09-04", occ="SPY260904C00600000", oi=300)
    nxt = _row(exp="2026-10-02", occ="SPY261002C00600000", oi=450)  # only +12%
    prev = {near["ckey"]: 1000, nxt["ckey"]: 400}
    tags = oh.oi_hygiene_tags([near, nxt], prev, today=today)
    assert tags[near["ckey"]]["rollover"] is False
    assert tags[nxt["ckey"]]["rollover"] is False


def test_both_legs_bled_not_a_roll():
    today = date(2026, 9, 2)
    near = _row(exp="2026-09-04", occ="SPY260904C00600000", oi=500)
    nxt = _row(exp="2026-10-02", occ="SPY261002C00600000", oi=300)
    prev = {near["ckey"]: 1000, nxt["ckey"]: 800}
    tags = oh.oi_hygiene_tags([near, nxt], prev, today=today)
    assert tags[near["ckey"]]["rollover"] is False


# ── earnings windows ─────────────────────────────────────────────────

def test_earnings_within_window_tagged():
    today = date(2026, 9, 2)   # Wed
    rows = [_row(under="NVDA")]
    # Friday same week = 2 trading days out
    tags = oh.oi_hygiene_tags(rows, {}, {"NVDA": "2026-09-04"}, today=today)
    assert tags[rows[0]["ckey"]]["earnings"] == {"days_to": 2}


def test_earnings_outside_window_not_tagged():
    today = date(2026, 9, 2)
    rows = [_row(under="NVDA")]
    tags = oh.oi_hygiene_tags(rows, {}, {"NVDA": "2026-10-15"}, today=today)
    assert tags[rows[0]["ckey"]]["earnings"] is None


def test_earnings_unknown_report_date_is_explicit():
    today = date(2026, 9, 2)
    rows = [_row(under="XYZ")]
    tags = oh.oi_hygiene_tags(rows, {}, {"XYZ": None}, today=today)
    assert tags[rows[0]["ckey"]]["earnings"] == {"unknown": True}


# ── shared why-suffix contract ───────────────────────────────────────

def test_why_suffix_contract():
    assert oh.oi_hygiene_why_suffix(None) == ""
    assert oh.oi_hygiene_why_suffix({}) == ""
    assert "rollover" in oh.oi_hygiene_why_suffix({"rollover": True})
    assert "earnings in 2 session(s)" in oh.oi_hygiene_why_suffix(
        {"earnings": {"days_to": 2}})
    assert "window unknown" in oh.oi_hygiene_why_suffix(
        {"earnings": {"unknown": True}})


# ── engine consumption ───────────────────────────────────────────────

def _engine_row(ckey, occ, oi=1200, vol=5000, score=95):
    return {
        "ckey": ckey, "occ": occ, "under": "SPY", "type": "call",
        "strike": 600.0, "exp": "2026-10-02", "dte": 30,
        "vol": vol, "oi": oi, "iv": 0.25, "delta": 0.5, "spot": 610.0,
        "vol_oi": vol / oi, "notional": vol * 100 * 600,
        "est_entry": 5.0, "premium": vol * 100 * 5.0, "_score": score,
    }


def test_engine_skips_rollover_oiconf():
    """A +50% overnight OI pop that is really a roll must not fire OICONF."""
    from services import flow_alerts as fa

    occ = "SPY261002C00600000"
    ckey = "SPY|call|600|2026-10-02"
    r = _engine_row(ckey, occ)
    prev = {ckey: 800}   # +50%
    tags = {ckey: {"expiring": False, "rollover": True, "earnings": None}}
    alerts = fa.eval_institutional([r], prev_oi=prev, oi_tags=tags)
    assert not [a for a in alerts if a["rule"] == "OICONF"]


def test_engine_earnings_oiconf_capped_below_gold():
    from services import flow_alerts as fa

    occ = "SPY261002C00600000"
    ckey = "SPY|call|600|2026-10-02"
    r = _engine_row(ckey, occ)
    r["est_entry"] = 60.0
    r["premium"] = r["vol"] * 100 * 60.0   # $30M → whale factor
    # score90 + whale + informed_band = three factors → GOLD normally;
    # the earnings tag must cap it.
    tags = {ckey: {"expiring": False, "rollover": False,
                   "earnings": {"days_to": 1}}}
    alerts = fa.eval_institutional([r], prev_oi={ckey: 800}, oi_tags=tags)
    oi = [a for a in alerts if a["rule"] == "OICONF"]
    assert oi, "OICONF still fires inside earnings windows (never-remove)"
    assert oi[0]["tier"] != "GOLD"
    assert "earnings" in oi[0]["why"]
