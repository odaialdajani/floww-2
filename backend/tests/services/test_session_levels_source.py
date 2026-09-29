"""C1.2 — the session level is reached over the real async bar path.

Three claims are pinned here, each against the specific old behavior that made
the level permanently absent while looking honest:

  1. The old wire was `public_api.fetch_public_bars`, a symbol that does not
     exist. The import sat inside a broad `except`, so the failure became a
     permanent NO_BARS.
  2. Composing an async bar fetch from a SYNC helper is not merely inelegant,
     it is broken: `asyncio.run` refuses to run inside a running loop. The
     caller therefore has to be async and must await the adapter.
  3. An exposure-weighted level over one venue's regular-session bars is not
     market VWAP, and the packet must not be readable without saying so.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SESSION_DATE = "2026-09-28"


def _bar(**over):
    row = {
        "date": f"{SESSION_DATE}T00:00:00Z",
        "open": 100.0,
        "high": 102.0,
        "low": 98.0,
        "close": 101.0,
        "volume": 1000,
        "session": "regular",
    }
    row.update(over)
    return row


@pytest.fixture
def source():
    """The source module, reloaded so monkeypatching is visible to it."""
    mod = importlib.import_module("services.session_levels_source")
    return importlib.reload(mod)


class TestTheOldWireWasDead:
    def test_the_symbol_the_old_helper_imported_does_not_exist(self):
        """This is the whole bug. It is asserted, not assumed."""
        from services import public_api

        assert hasattr(public_api, "fetch_public_bars") is False

    def test_the_replacement_is_bound_at_module_scope_not_inside_a_try(self):
        """A local import inside a broad `except` is what hid the old one.

        If this ever moves into a function, a future rename silently returns
        NO_BARS again. The static check below is the guard.
        """
        from services import public_api_adapter

        source = importlib.import_module("services.session_levels_source")
        assert source.fetch_bars_from_public_api is public_api_adapter.fetch_bars_from_public_api

        tree = ast.parse(Path(source.__file__).read_text(encoding="utf-8"))
        module_level_imports = [
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("public_api_adapter")
        ]
        assert module_level_imports, "the adapter must be imported at module scope, not lazily"


class TestNoNestedEventLoops:
    FORBIDDEN = ("asyncio.run", "run_until_complete", "new_event_loop", "set_event_loop")

    @staticmethod
    def _called_names(tree: ast.AST) -> set[str]:
        """Every dotted function/attribute name actually invoked in the code.

        Resolved from the AST rather than by grepping the file text, so a
        docstring that NAMES these constructs in order to explain why they are
        forbidden cannot trip the check. Prose is not a call site.
        """
        names: set[str] = set()

        def dotted(node: ast.AST) -> str | None:
            parts: list[str] = []
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
                return ".".join(reversed(parts))
            return None

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = dotted(node.func)
                if name:
                    names.add(name)
            elif isinstance(node, ast.Attribute):
                name = dotted(node)
                if name:
                    names.add(name)
            elif isinstance(node, ast.Name):
                names.add(node.id)
        return names

    def test_module_invokes_no_event_loop_constructs(self):
        path = BACKEND / "services" / "session_levels_source.py"
        assert path.is_file()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used = self._called_names(tree)
        found = sorted(
            name
            for name in self.FORBIDDEN
            if any(name == u or u.endswith(f".{name}") for u in used)
        )
        assert found == [], f"session_levels_source.py calls {found}; await the adapter instead"

    async def test_the_old_sync_wrapper_pattern_is_broken_inside_a_running_loop(self):
        """Why the composition must be async, demonstrated rather than asserted.

        This is the shape the private helper actually had: a sync function that
        reaches for a coroutine. This test body is itself `async`, so a loop is
        already running when `old_sync_wrapper` calls `asyncio.run` — which is
        exactly the condition the app's request handler is always in, and
        exactly why the caller swallowed the error and shipped a permanent
        NO_BARS.
        """

        async def a_real_coroutine() -> str:
            return "bars"

        def old_sync_wrapper() -> str:
            return asyncio.run(a_real_coroutine())

        # Proved live, not assumed: this test is running inside a loop.
        asyncio.get_running_loop()
        with pytest.raises(RuntimeError, match="cannot be called from a running event loop"):
            old_sync_wrapper()

    def test_the_real_caller_works_inside_an_already_running_loop(self, source, monkeypatch):
        """The positive proof: awaited directly, it composes cleanly."""
        seen: list[str] = []

        async def fake_bars(ticker, timeframe="1Day", limit=100, sessions="regular"):
            seen.append(ticker)
            return [_bar()]

        monkeypatch.setattr(source, "fetch_bars_from_public_api", fake_bars)

        async def caller():
            # Deliberately nested inside another coroutine: a live loop exists.
            return await source.session_exposure_level_for_ticker("spy", SESSION_DATE)

        out = asyncio.run(caller())
        assert out["status"] == "ok"
        assert out["value"] == pytest.approx(100.3333333, rel=1e-6)
        assert seen == ["SPY"], "the ticker must be normalized and passed to the adapter"


class TestLabelingIsNotMarketVwap:
    def test_packet_never_claims_to_be_market_vwap(self, source, monkeypatch):
        async def fake_bars(*a, **k):
            return [_bar()]

        monkeypatch.setattr(source, "fetch_bars_from_public_api", fake_bars)
        out = asyncio.run(source.session_exposure_level_for_ticker("SPY", SESSION_DATE))

        assert out["is_market_vwap"] is False
        assert "vwap" not in out["label"].lower()
        assert "NOT market VWAP" in out["not_market_vwap_because"]

    def test_unavailable_packet_is_shaped_identically_and_still_not_vwap(self, source, monkeypatch):
        async def no_bars(*a, **k):
            return None

        monkeypatch.setattr(source, "fetch_bars_from_public_api", no_bars)
        out = asyncio.run(source.session_exposure_level_for_ticker("SPY", SESSION_DATE))

        assert out["status"] == "unavailable"
        assert out["value"] is None, "unavailable is null, never a substituted price"
        assert out["is_market_vwap"] is False
        assert out["label"] == out.get("label"), "label present on the failure path too"


class TestUnavailableNeverBecomesZero:
    async def _call(self, source, monkeypatch, ret, ticker="SPY", date=SESSION_DATE):
        async def fake_bars(*a, **k):
            return ret

        monkeypatch.setattr(source, "fetch_bars_from_public_api", fake_bars)
        return await source.session_exposure_level_for_ticker(ticker, date)

    def test_adapter_returning_none_is_no_bars_not_zero(self, source, monkeypatch):
        out = asyncio.run(self._call(source, monkeypatch, None))
        assert out["value"] is None
        assert out["reason"] == "NO_BARS"
        assert out["bars_used"] == 0

    def test_bars_without_volume_are_skipped_not_treated_as_zero_volume(self, source, monkeypatch):
        out = asyncio.run(
            self._call(source, monkeypatch, [_bar(volume=0), _bar(volume=None)])
        )
        assert out["value"] is None
        assert out["reason"] == "NO_VOLUME"
        assert out["bars_skipped"] == 2

    def test_a_mix_keeps_the_real_subtotal_and_reports_the_skip(self, source, monkeypatch):
        out = asyncio.run(
            self._call(source, monkeypatch, [_bar(volume=0), _bar(volume=500)])
        )
        assert out["status"] == "ok"
        assert out["bars_used"] == 1
        assert out["bars_skipped"] == 1
        assert out["value"] == pytest.approx(100.3333333, rel=1e-6)

    def test_a_different_session_date_is_not_silently_substituted(self, source, monkeypatch):
        out = asyncio.run(self._call(source, monkeypatch, [_bar()], date="2020-01-02"))
        assert out["value"] is None
        assert out["reason"] == "NO_VOLUME", "zero usable bars, and it says so"

    def test_missing_ticker_is_refused_before_any_fetch(self, source, monkeypatch):
        calls: list[str] = []

        async def counting(ticker, **k):
            calls.append(ticker)
            return []

        monkeypatch.setattr(source, "fetch_bars_from_public_api", counting)
        out = asyncio.run(source.session_exposure_level_for_ticker("", SESSION_DATE))
        assert out["value"] is None
        assert out["reason"] == "NO_TICKER"
        assert calls == [], "a blank ticker must not reach the provider"


class TestProvenance:
    def test_source_dates_come_from_the_bars_that_were_used(self, source, monkeypatch):
        rows = [
            _bar(date=f"{SESSION_DATE}T00:00:00Z", volume=100),
            _bar(date=f"{SESSION_DATE}T00:00:00Z", volume=200),
        ]

        async def fake_bars(*a, **k):
            return rows

        monkeypatch.setattr(source, "fetch_bars_from_public_api", fake_bars)
        out = asyncio.run(source.session_exposure_level_for_ticker("SPY", SESSION_DATE))
        assert len(out["source_dates"]) == 2
        assert out["bar_source"].endswith("fetch_bars_from_public_api")
        assert out["timeframe"] == "1Day"

    def test_intraday_bars_are_excluded_by_the_session_date_prefix(self, source, monkeypatch):
        """Regular-session scope is enforced, not assumed."""
        rows = [
            _bar(session="pre", volume=1000),
            _bar(session="regular", volume=1000),
        ]

        async def fake_bars(*a, **k):
            return rows

        monkeypatch.setattr(source, "fetch_bars_from_public_api", fake_bars)
        out = asyncio.run(source.session_exposure_level_for_ticker("SPY", SESSION_DATE))
        assert out["bars_used"] == 1
        assert out["bars_skipped"] == 1


def test_pure_math_module_is_unchanged_and_still_importable():
    """The domain layer keeps its no-I/O guarantee; this slice added a caller,
    not a second implementation."""
    from domain.session_levels import SESSION_LEVEL_VERSION, session_exposure_level

    assert SESSION_LEVEL_VERSION == "session-exposure-level.v1"
    out = session_exposure_level([_bar()], session_date=SESSION_DATE)
    assert out["value"] == pytest.approx(100.3333333, rel=1e-6)
    assert "asyncio" not in (Path(BACKEND / "domain" / "session_levels.py").read_text(encoding="utf-8"))
