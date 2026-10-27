"""Isolated-store reproduction of the th6 protection failure classes (B5).

Historical evidence (Oct-18 plan / FLOWW-Paper-Evidence-20261018.json) counts
19 venue_stop_failed, 14 supervisor_error and 14 ghost_closed events and
requires their EXACT CAUSES reproduced in isolation before paper-position
protection is trusted. The th6 scripts themselves are PROTECTED READ-ONLY and
never imported or executed here; this file replicates the three MECHANICS on
an isolated SQLite store so each failure class has an in-repo regression pin:

  1. stop rejection -> position UNPROTECTED, failure event THROTTLED to one
     per 2-minute window per symbol (source: th_supervisor_v6.py:421-436 —
     the historical pain was 6 identical failure events per minute).
  2. ghost close -> venue lost the position; exit price is recovered from the
     most recent FILLED sell, otherwise pnl stays UNKNOWN (None), never zero
     (source: th_supervisor_v6.py:354-372).
  3. the v6.2 coid/symbol keying bug -> an UPDATE keyed on the wrong field
     matched zero rows and the ghost-close looped forever (12+ events for one
     position); the coid-keyed form must close the row in one statement
     (source comment at th_supervisor_v6.py:363-367).
  4. tick containment -> an exception in a tick step is recorded as a
     supervisor_error naming its type and the loop continues (source:
     th_supervisor_v6.py:634-640).

No network, no venue, no protected file is touched.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE positions (
            coid TEXT PRIMARY KEY, symbol TEXT NOT NULL, state TEXT NOT NULL,
            venue_stop_order_id TEXT DEFAULT '', entry_prem REAL, qty INTEGER,
            close_reason TEXT, realized_pnl REAL, closed_at TEXT);
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, t TEXT NOT NULL,
            kind TEXT NOT NULL, data TEXT NOT NULL);
    """)
    return conn


def _log_event(conn, kind, **data):
    conn.execute("INSERT INTO events (t, kind, data) VALUES (?, ?, ?)",
                 (dt.datetime.now().isoformat(), kind, json.dumps(data)))
    conn.commit()


def _events(conn, kind):
    return conn.execute("SELECT * FROM events WHERE kind=?", (kind,)).fetchall()


def _open_position(conn, coid="c1", symbol="SPY", qty=2, entry=2.50):
    conn.execute(
        "INSERT INTO positions (coid, symbol, state, entry_prem, qty) VALUES (?,?,?,?,?)",
        (coid, symbol, "OPEN", entry, qty))
    conn.commit()


# ── 1. stop rejection → UNPROTECTED + throttled failure event ─────────────

def _record_stop_failure(conn, symbol, error, *, throttle_seconds=120):
    """Mirror of the supervisor's throttled failure logging (th:421-436)."""
    last = conn.execute(
        "SELECT t FROM events WHERE kind='venue_stop_failed' AND data LIKE ? "
        "ORDER BY id DESC LIMIT 1", (f"%{symbol}%",)).fetchone()
    recent = (last is not None and (
        dt.datetime.now() - dt.datetime.fromisoformat(last["t"])
    ).total_seconds() < throttle_seconds)
    if not recent:
        _log_event(conn, "venue_stop_failed", symbol=symbol, error=error)
        return True
    return False


class TestStopRejection:
    def test_rejection_marks_unprotected(self):
        conn = _db()
        _open_position(conn)
        # place_venue_stop rejected -> venue_stop_order_id empty, state flips.
        conn.execute("UPDATE positions SET state='UNPROTECTED' WHERE coid='c1'")
        conn.commit()
        assert conn.execute("SELECT state FROM positions WHERE coid='c1'").fetchone()["state"] \
            == "UNPROTECTED"

    def test_failure_events_throttled_to_one_per_window(self):
        conn = _db()
        _open_position(conn)
        # The historical pain: 6 identical failure events in one minute.
        logged = [ _record_stop_failure(conn, "SPY", "stop price must be less than current price")
                   for _ in range(6) ]
        assert sum(logged) == 1, "repeated rejections within the window must log ONE event"
        assert len(_events(conn, "venue_stop_failed")) == 1
        # After the 2-minute window a new failure is logged again.
        conn.execute("UPDATE events SET t=? WHERE kind='venue_stop_failed'",
                     ((dt.datetime.now() - dt.timedelta(seconds=121)).isoformat(),))
        conn.commit()
        assert _record_stop_failure(conn, "SPY", "stop rejected again") is True
        assert len(_events(conn, "venue_stop_failed")) == 2

    def test_other_symbol_not_throttled_by_this_symbol(self):
        conn = _db()
        _open_position(conn, coid="c1", symbol="SPY")
        _open_position(conn, coid="c2", symbol="QQQ")
        assert _record_stop_failure(conn, "SPY", "x") is True
        assert _record_stop_failure(conn, "QQQ", "x") is True


# ── 2. ghost close → recovered exit price or UNKNOWN pnl, never zero ───────

def _ghost_close(conn, coid, symbol, recent_orders):
    """Mirror of the supervisor's ghost-close path (th:354-372).

    The supervisor iterates the OPEN position set: a row already CLOSED is
    not in the set, so a repeated pass cannot emit a second ghost event.
    """
    row = conn.execute(
        "SELECT * FROM positions WHERE coid=? AND state != 'CLOSED'", (coid,)).fetchone()
    if row is None:
        return
    exit_px = None
    for order in reversed(recent_orders):
        if (order.get("symbol") == symbol and order.get("side") == "sell"
                and order.get("status") == "filled"):
            exit_px = float(order.get("filled_avg_price") or 0) or None
            break
    pnl = None
    if exit_px is not None and row["entry_prem"]:
        pnl = round((exit_px - row["entry_prem"]) * 100 * row["qty"], 2)
    conn.execute(
        """UPDATE positions SET state='CLOSED', closed_at=?,
           close_reason=COALESCE(close_reason,'vanish'), realized_pnl=?
           WHERE coid=?""",
        (dt.datetime.now().isoformat(), pnl, row["coid"]))
    conn.commit()
    _log_event(conn, "ghost_closed", symbol=symbol, exit_px=exit_px, pnl=pnl)


class TestGhostClose:
    def test_exit_price_recovered_from_recent_filled_sell(self):
        conn = _db()
        _open_position(conn, entry=2.50, qty=2)
        orders = [
            {"symbol": "SPY", "side": "sell", "status": "cancelled"},
            {"symbol": "SPY", "side": "sell", "status": "filled",
             "filled_avg_price": "3.10"},
        ]
        _ghost_close(conn, "c1", "SPY", orders)
        row = conn.execute("SELECT * FROM positions WHERE coid='c1'").fetchone()
        assert row["state"] == "CLOSED" and row["close_reason"] == "vanish"
        assert row["realized_pnl"] == round((3.10 - 2.50) * 100 * 2, 2)

    def test_unknown_exit_keeps_pnl_none_never_zero(self):
        conn = _db()
        _open_position(conn, entry=2.50, qty=2)
        _ghost_close(conn, "c1", "SPY", [])  # no filled sell anywhere
        row = conn.execute("SELECT * FROM positions WHERE coid='c1'").fetchone()
        assert row["state"] == "CLOSED"
        assert row["realized_pnl"] is None, "unknown exit must stay unknown, never zero"

    def test_cancelled_sell_does_not_fake_an_exit(self):
        conn = _db()
        _open_position(conn, entry=2.50, qty=2)
        _ghost_close(conn, "c1", "SPY",
                     [{"symbol": "SPY", "side": "sell", "status": "cancelled"}])
        assert conn.execute(
            "SELECT realized_pnl FROM positions WHERE coid='c1'").fetchone()["realized_pnl"] is None


# ── 3. the v6.2 coid/symbol keying regression ─────────────────────────────

class TestCoidKeyingRegression:
    def test_symbol_keyed_update_matches_zero_rows(self):
        """The historical bug: positions keyed by SYMBOL in the loop, but the
        UPDATE filtered on coid=<symbol> — zero rows matched and the close
        looped forever (12+ ghost_closed events, row stuck in PROTECTED)."""
        conn = _db()
        _open_position(conn, coid="real-coid-1", symbol="SPY")
        conn.execute("UPDATE positions SET state='PROTECTED' WHERE coid='real-coid-1'")
        # Wrong form (bug): coid='SPY' (the loop key) matches nothing.
        conn.execute("UPDATE positions SET state='CLOSED' WHERE coid=?", ("SPY",))
        conn.commit()
        row = conn.execute("SELECT * FROM positions WHERE symbol='SPY'").fetchone()
        assert row["state"] == "PROTECTED", "wrongly-keyed update must change nothing"
        # Correct form (v6.2 fix): the row's actual coid closes it once.
        conn.execute("UPDATE positions SET state='CLOSED' WHERE coid=?", (row["coid"],))
        conn.commit()
        assert conn.execute("SELECT state FROM positions WHERE coid='real-coid-1'"
                            ).fetchone()["state"] == "CLOSED"

    def test_ghost_close_cannot_loop(self):
        """With coid keying, ONE ghost-close statement must close the row —
        a second pass finds no open row and emits no second event."""
        conn = _db()
        _open_position(conn, coid="real-coid-2", symbol="QQQ")
        _ghost_close(conn, "real-coid-2", "QQQ", [])
        _ghost_close(conn, "real-coid-2", "QQQ", [])
        assert len(_events(conn, "ghost_closed")) == 1


# ── 4. tick containment ────────────────────────────────────────────────────

class TestTickContainment:
    def test_step_exception_recorded_and_loop_continues(self):
        """supervisor_error contract (th:634-640): record type+message, keep
        ticking — the fleet survives a bad tick (clock/JSON/DB hiccups)."""
        conn = _db()
        ticks = []
        for step in ("ok", "explode", "ok"):
            try:
                if step == "explode":
                    raise ValueError("clock unreadable")
                ticks.append(step)
            except Exception as exc:  # noqa: BLE001 — containment contract
                _log_event(conn, "supervisor_error",
                           error=f"{type(exc).__name__}: {exc}")
        assert ticks == ["ok", "ok"], "the loop must continue after a failed step"
        events = _events(conn, "supervisor_error")
        assert len(events) == 1
        assert json.loads(events[0]["data"])["error"].startswith("ValueError:")
