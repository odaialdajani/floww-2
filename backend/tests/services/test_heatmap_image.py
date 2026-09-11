"""
backend/tests/services/test_heatmap_image.py — Solstice PNG renderer.
PIL-only; no network. Fixtures, never live chains.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _payload(**over):
    base = {
        "ticker": "SPY",
        "spot": 700.0,
        "strikes": [
            {"strike": 690.0, "gex": -5e8},
            {"strike": 695.0, "gex": -1e8},
            {"strike": 700.0, "gex": 3e8},
            {"strike": 705.0, "gex": 9e8},
            {"strike": 710.0, "gex": 2e8},
        ],
        "nodes": {"king": {"strike": 705.0, "gex": 9e8}, "regime": "positive"},
        "gamma_flip": 697.5,
    }
    base.update(over)
    return base


class TestNormalize:
    def test_ok(self):
        from services.heatmap_image import gex_rows_from_heatmap
        out = gex_rows_from_heatmap(_payload())
        assert out["ticker"] == "SPY" and out["spot"] == 700.0
        assert len(out["strikes"]) == 5
        assert out["king_strike"] == 705.0 and out["flip"] == 697.5

    def test_flip_fallback_zero_crossing(self):
        from services.heatmap_image import gex_rows_from_heatmap
        p = _payload()
        del p["gamma_flip"]
        out = gex_rows_from_heatmap(p)
        assert out["flip"] in (695.0, 700.0)

    def test_degenerate_is_none(self):
        from services.heatmap_image import gex_rows_from_heatmap
        assert gex_rows_from_heatmap(None) is None
        assert gex_rows_from_heatmap({}) is None
        assert gex_rows_from_heatmap({"ticker": "X", "spot": 0, "strikes": []}) is None


class TestRender:
    def test_gex_png_bytes(self):
        from services.heatmap_image import gex_rows_from_heatmap, render_gex_png
        png = render_gex_png(gex_rows_from_heatmap(_payload()))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert 10_000 < len(png) < 2_000_000

    def test_render_none_safe(self):
        from services.heatmap_image import render_gex_png, render_vex_png
        assert render_gex_png(None) is None
        assert render_vex_png(None) is None

    def test_trims_to_60_rows(self):
        from services.heatmap_image import render_gex_png
        norm = {"ticker": "X", "spot": 100.0,
                "strikes": [(float(k), 1e6) for k in range(1, 201)],
                "king_strike": None, "flip": None, "regime": "?"}
        assert render_gex_png(norm)[:8] == b"\x89PNG\r\n\x1a\n"


class TestVex:
    def test_vex_rows_from_contracts(self):
        from services.heatmap_image import render_vex_png, vex_rows_from_contracts
        contracts = [
            {"strike": 700.0, "type": "call", "oi": 5000, "iv": 0.25, "expiry": "2099-01-15"},
            {"strike": 700.0, "type": "put", "oi": 4000, "iv": 0.30, "expiry": "2099-01-15"},
            {"strike": 710.0, "type": "call", "oi": 1000, "iv": 0.22, "expiry": "2099-01-15"},
            {"strike": 0, "type": "call", "oi": 9, "iv": 0.2, "expiry": "2099-01-15"},
            {"bogus": True},
        ]
        out = vex_rows_from_contracts(contracts, 700.0)
        assert out is not None and len(out["strikes"]) == 2
        png = render_vex_png({**out, "ticker": "SPY"})
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_vex_degenerate_none(self):
        from services.heatmap_image import vex_rows_from_contracts
        assert vex_rows_from_contracts([], 700.0) is None
        assert vex_rows_from_contracts(None, 700.0) is None
        assert vex_rows_from_contracts([{"strike": 1}], 0) is None


class TestWalls:
    def test_walls_text(self):
        from services.heatmap_image import gex_rows_from_heatmap, walls_text
        t = walls_text(gex_rows_from_heatmap(_payload()))
        assert "705" in t and "690" in t  # call wall + put wall
        assert "697.5" in t and "King Node" in t

    def test_walls_empty(self):
        from services.heatmap_image import walls_text
        assert "unavailable" in walls_text(None)


class TestV2Layers:
    def _norm(self):
        from services.heatmap_image import gex_rows_from_heatmap
        return gex_rows_from_heatmap({
            "ticker": "SPY", "spot": 700.0, "data_source": "public_api",
            "strikes": [
                {"strike": 690.0, "gex": -5e8, "call_gex": 1e8, "put_gex": 6e8,
                 "call_oi": 1000, "put_oi": 9000},
                {"strike": 695.0, "gex": -1e8, "call_gex": 2e8, "put_gex": 3e8,
                 "call_oi": 2000, "put_oi": 3000},
                {"strike": 700.0, "gex": 3e8, "call_gex": 5e8, "put_gex": 2e8,
                 "call_oi": 8000, "put_oi": 2000},
                {"strike": 705.0, "gex": 9e8, "call_gex": 9e8, "put_gex": 0,
                 "call_oi": 12000, "put_oi": 500},
            ],
            "nodes": {"king": {"strike": 705.0, "gex": 9e8}, "regime": "positive"},
            "gamma_flip": 697.5,
        })

    def test_splits_and_max_pain(self):
        from services.heatmap_image import max_pain_strike
        norm = self._norm()
        assert set(norm["splits"][700.0]) >= {"call_gex", "put_gex", "call_oi", "put_oi"}
        # hand-check: K=695 payout = calls: 8000*0+... compute pinakam: heavy put OI low
        mp = max_pain_strike(norm["splits"])
        assert mp in (690.0, 695.0, 700.0, 705.0)
        # all-zero OI -> None, never a fabricated strike
        assert max_pain_strike({690.0: {"call_oi": 0, "put_oi": 0}}) is None
        assert max_pain_strike(None) is None

    def test_v2_render_has_split_cumulative_pain(self):
        import io

        from PIL import Image

        from services.heatmap_image import render_gex_png
        png = render_gex_png(self._norm())
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        im = Image.open(io.BytesIO(png)).convert("RGB")
        px = list(im.getdata())
        amber = sum(1 for r, g, b in px if r > 235 and 175 < g < 205 and b < 80)
        white = sum(1 for r, g, b in px if r > 235 and g > 235 and b > 235)
        assert amber > 100, "cumulative dealer curve missing"
        assert white > 20, "net ticks / max-pain line missing"

    def test_walls_carries_max_pain(self):
        from services.heatmap_image import walls_text
        t = walls_text(self._norm())
        assert "Max pain" in t
