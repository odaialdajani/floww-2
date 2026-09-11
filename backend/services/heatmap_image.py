"""
backend/services/heatmap_image.py — Solstice GEX/VEX chart renderer for Discord.

Renders the Solstice dealer-positioning view (strike ladder with signed
exposure bars, spot line, King Node, gamma-flip level) to PNG bytes with
PIL only — no matplotlib dependency, no browser, works in the bot process.

Data contracts (defensive: every field optional, degenerate → None):
- GEX input: heatmap payload shape from server.build_heatmap:
  {ticker, spot, strikes: [{strike, gex, ...}], nodes: {king: {strike, gex},
   regime}, gamma_flip | gammaFlip}. Missing flip → zero-crossing fallback.
- VEX input: raw chain contracts [{strike, type, oi, iv, expiry/T}] +
  spot; vomma via BSCalculator, aggregated per strike (same dollar scale
  as GEX: sign × vomma × OI × 100 × spot² × 0.01).

All renderers are pure (inputs → bytes). Fetching lives in the small
async helpers (get_heatmap_data / get_chain_contracts), which fail-open
to None so commands reply "unavailable" instead of crashing.
"""
from __future__ import annotations

import contextlib
import io
import logging
import math
from typing import Any

log = logging.getLogger(__name__)

W, H = 900, 640
BG = (10, 12, 18)
PANEL = (16, 20, 30)
GRID = (255, 255, 255, 18)
TEXT = (240, 244, 250)
MUTED = (150, 160, 175)
POS = (232, 201, 106)     # +GEX gold (Pika)
NEG = (162, 103, 255)     # -GEX purple (Barney)
VPOS = (56, 189, 248)     # +VEX cyan
VNEG = (244, 114, 182)    # -VEX pink
SPOT_C = (34, 197, 94)
FLIP_C = (239, 68, 68)


def _font(size: int):
    try:
        from PIL import ImageFont

        for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Arial.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()
    except Exception:
        return None


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


def gex_rows_from_heatmap(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize a build_heatmap payload to render inputs. None when unusable."""
    if not isinstance(payload, dict):
        return None
    try:
        spot = float(payload.get("spot") or 0)
    except (TypeError, ValueError):
        spot = 0
    strikes: list[tuple[float, float]] = []
    splits: dict[float, dict[str, float]] = {}
    for s in payload.get("strikes", []) or []:
        try:
            k = float(s.get("strike"))
            g = float(s.get("gex", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if k <= 0:
            continue
        strikes.append((k, g))
        with contextlib.suppress(TypeError, ValueError):
            splits[k] = {
                "call_gex": float(s.get("call_gex", 0) or 0),
                "put_gex": float(s.get("put_gex", 0) or 0),
                "call_oi": float(s.get("call_oi", 0) or 0),
                "put_oi": float(s.get("put_oi", 0) or 0),
            }
    if not strikes or spot <= 0:
        return None
    strikes.sort()
    nodes = payload.get("nodes", {}) or {}
    king = nodes.get("king", {}) or {}
    try:
        king_strike = float(king.get("strike")) if king.get("strike") is not None else None
    except (TypeError, ValueError):
        king_strike = None
    flip = payload.get("gamma_flip", payload.get("gammaFlip", None))
    try:
        flip = float(flip) if flip is not None else None
    except (TypeError, ValueError):
        flip = None
    if flip is None:
        # zero-crossing fallback on the sorted curve
        for (k0, g0), (k1, g1) in zip(strikes, strikes[1:], strict=False):
            if (g0 <= 0) != (g1 <= 0):
                flip = k0 if abs(g0) < abs(g1) else k1
                break
    return {
        "ticker": str(payload.get("ticker") or "?").upper(),
        "spot": spot,
        "strikes": strikes,
        "splits": splits,
        "king_strike": king_strike,
        "flip": flip,
        "regime": str(nodes.get("regime") or "?"),
        "source": str(payload.get("data_source") or "chain"),
    }


def max_pain_strike(splits: dict[float, dict[str, float]] | None) -> float | None:
    """Classic max-pain strike from per-strike OI (no quotes needed).

    Minimizes total option-buyer payout evaluated at each candidate strike:
    Σ call_OI × max(K−Kc,0) + Σ put_OI × max(Kp−K,0). None without OI.
    """
    if not splits:
        return None
    calls = [(k, v.get("call_oi", 0) or 0) for k, v in splits.items()]
    puts = [(k, v.get("put_oi", 0) or 0) for k, v in splits.items()]
    if not any(oi > 0 for _, oi in calls + puts):
        return None
    best: float | None = None
    best_val = math.inf
    for k in splits:
        val = (sum(oi * max(k - kc, 0) for kc, oi in calls)
               + sum(oi * max(kp - k, 0) for kp, oi in puts))
        if val < best_val:
            best_val, best = val, k
    return best


def vex_rows_from_contracts(
    contracts: list[dict[str, Any]] | None, spot: float
) -> dict[str, Any] | None:
    """Aggregate per-strike VEX from chain contracts (BS vomma). None when unusable."""
    try:
        s = float(spot)
    except (TypeError, ValueError):
        s = 0
    if s <= 0 or not contracts:
        return None
    try:
        from services.bs_calculator import BSCalculator
    except Exception as e:
        log.warning("heatmap VEX unavailable (bs_calculator): %s", e)
        return None
    ks, ts, ivs, kinds, ois = [], [], [], [], []
    for c in contracts:
        try:
            if not isinstance(c, dict):
                continue
            k = float(c.get("strike") or 0)
            oi = float(c.get("oi") or c.get("openInterest") or 0)
            iv_raw = c.get("iv", c.get("impliedVolatility", 0)) or 0
            iv = float(iv_raw)
            if iv >= 3:  # percent convention
                iv /= 100.0
            exp = str(c.get("expiry") or c.get("expiration") or "")
            t = _dte_years(exp)
            typ = str(c.get("type") or "").lower()
            if k <= 0 or oi <= 0 or iv <= 0 or t is None or t <= 0:
                continue
            ks.append(k)
            ts.append(t)
            ivs.append(iv)
            kinds.append(0 if typ.startswith("c") else 1)
            ois.append(oi)
        except (TypeError, ValueError):
            continue
    if not ks:
        return None
    try:
        import numpy as np

        calc = BSCalculator(s)
        greeks = calc.compute_chain(np.array(ks), np.array(ts), np.array(ivs), np.array(kinds))
        vommas = [float(v) for v in greeks["vomma"]]
    except Exception as e:
        log.warning("heatmap VEX compute failed: %s", e)
        return None
    scale = s * s * 0.01 * 100.0
    agg: dict[float, float] = {}
    for k, v, oi, kind in zip(ks, vommas, ois, kinds, strict=False):
        if not math.isfinite(v):
            continue
        sign = 1.0 if kind == 0 else -1.0
        agg[k] = agg.get(k, 0.0) + sign * v * oi * scale
    if not agg:
        return None
    return {"strikes": sorted(agg.items()), "spot": s}


def _dte_years(exp: str) -> float | None:
    from datetime import date

    try:
        d = date.fromisoformat(str(exp)[:10])
    except (TypeError, ValueError):
        return None
    delta = (d - date.today()).days
    return max(delta, 0) / 365.0 if delta >= 0 else None


def _render(rows: list[tuple[float, float]], *, ticker: str, spot: float,
            kind: str, king_strike: float | None, flip: float | None,
            regime: str, sub: str, splits: dict | None = None,
            cumulative: bool = True, max_pain: float | None = None,
            footer: str | None = None) -> bytes | None:
    """Shared strike-ladder renderer. kind ∈ {GEX, VEX}.

    v2 layers (GammaGrid/gex-dash vocabulary, own rendering):
    - call/put SPLIT bars when splits are provided (gold up / purple down),
      with a white net tick per strike; else single net bars (legacy).
    - cumulative net-GEX curve seeded at spot, radiating outward (amber).
    - max-pain dotted level + footer provenance line.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        log.warning("heatmap render unavailable (no PIL)")
        return None
    if not rows:
        return None
    pos_c, neg_c = (POS, NEG) if kind == "GEX" else (VPOS, VNEG)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img, "RGBA")
    f_title, f_body, f_small = _font(30), _font(19), _font(15)
    top, bottom, left, right = 86, H - 44, 92, W - 150
    d.rectangle([0, 0, W, H], fill=BG)
    net = sum(g for _, g in rows)
    d.text((24, 14), f"{ticker} {kind} ladder", font=f_title, fill=TEXT)
    d.text((24, 50), f"spot {spot:.2f} · net {_fmt_money(net)} · regime {regime} · {sub}",
           font=f_body, fill=MUTED)
    ks = [k for k, _ in rows]
    lo, hi = min(min(ks), spot), max(max(ks), spot)
    pad = (hi - lo) * 0.04 or 1.0
    lo -= pad
    hi += pad

    def y_of(k: float) -> float:
        return bottom - (k - lo) / (hi - lo) * (bottom - top)

    max_abs = max((abs(g) for _, g in rows), default=0) or 1.0
    n = len(rows)
    row_h = max(2.0, (bottom - top) / max(n, 1) - 2)
    use_split = isinstance(splits, dict) and any(
        (splits.get(k) or {}).get("call_gex") or (splits.get(k) or {}).get("put_gex")
        for k, _ in rows)
    for i, (k, g) in enumerate(rows):
        y = top + i * ((bottom - top) / max(n, 1)) + 1
        if use_split:
            sp = splits.get(k) or {}
            cg = abs(float(sp.get("call_gex") or 0))
            pg = abs(float(sp.get("put_gex") or 0))
            # stacked diverging bar: gold calls up, purple puts down
            wdt_c = cg / max_abs * (right - left - 120)
            wdt_p = pg / max_abs * (right - left - 120)
            yc = y + row_h / 2
            d.rounded_rectangle([left + 118, yc - row_h / 2, left + 118 + max(2, wdt_c), yc],
                                radius=1, fill=pos_c)
            d.rounded_rectangle([left + 118, yc, left + 118 + max(2, wdt_p), yc + row_h / 2],
                                radius=1, fill=neg_c)
            # white net tick
            nx = left + 118 + abs(g) / max_abs * (right - left - 120)
            d.line([(nx, y), (nx, y + row_h)], fill=(255, 255, 255, 220), width=2)
        else:
            wdt = abs(g) / max_abs * (right - left - 120)
            color = pos_c if g >= 0 else neg_c
            d.rounded_rectangle([left + 118, y, left + 118 + max(3, wdt), y + row_h],
                                radius=2, fill=color)
        if i % max(1, n // 14) == 0:
            d.text((8, y - 4), f"{k:g}", font=f_small, fill=MUTED)
    if cumulative and n > 2:
        # dealer curve: net exposure accumulated outward from spot (gex-dash
        # vocabulary). Seeded at the strike nearest spot, own normalization.
        order = sorted(range(n), key=lambda i: abs(rows[i][0] - spot))
        seq: list[tuple[float, float]] = []
        run = 0.0
        for i in order:
            run += rows[i][1]
            seq.append((rows[i][0], run))
        seq.sort(key=lambda kv: kv[0])
        y_by_k = {k: top + i * ((bottom - top) / max(n, 1)) + 1 + row_h / 2
                  for i, (k, _) in enumerate(rows)}
        cmax = max((abs(v) for _, v in seq), default=0) or 1.0
        pts = [(left + 118 + abs(v) / cmax * (right - left - 120) * 0.92, y_by_k[k])
               for k, v in seq]
        if len(pts) > 1:
            d.line(pts, fill=(251, 191, 36, 235), width=2, joint="curve")
            for x, y in pts[:: max(1, len(pts) // 24)]:
                d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(251, 191, 36, 235))
    # spot + flip + king + max-pain lines
    d.line([(left, y_of(spot)), (W - 8, y_of(spot))], fill=SPOT_C, width=2)
    d.text((W - 138, y_of(spot) - 22), f"spot {spot:.2f}", font=f_small, fill=SPOT_C)
    if flip and lo <= flip <= hi:
        for xx in range(left, W - 8, 12):
            d.line([(xx, y_of(flip)), (xx + 6, y_of(flip))], fill=FLIP_C, width=2)
        d.text((W - 138, y_of(flip) + 4), f"flip {flip:g}", font=f_small, fill=FLIP_C)
    if king_strike and lo <= king_strike <= hi:
        yk = y_of(king_strike)
        d.text((left + 2, yk - 22), "★ KING", font=f_body, fill=(232, 201, 106))
        d.line([(left, yk), (W - 8, yk)], fill=(232, 201, 106, 90), width=1)
    if max_pain and lo <= max_pain <= hi:
        ymp = y_of(max_pain)
        for xx in range(left, W - 8, 8):
            d.line([(xx, ymp), (xx + 4, ymp)], fill=(255, 255, 255, 150), width=1)
        d.text((left + 2, ymp + 2), f"MP {max_pain:g}", font=f_small, fill=(255, 255, 255, 200))
    # right-side scale
    d.text((W - 132, top), _fmt_money(max_abs), font=f_small, fill=MUTED)
    d.text((W - 132, bottom - 18), "0", font=f_small, fill=MUTED)
    if footer:
        d.text((left, H - 26), footer[:110], font=f_small, fill=MUTED)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_gex_png(norm: dict[str, Any] | None, *, max_rows: int = 60) -> bytes | None:
    """Render normalized GEX rows to PNG. None when unusable."""
    if not norm:
        return None
    rows = norm["strikes"]
    splits = norm.get("splits") if isinstance(norm.get("splits"), dict) else None
    if len(rows) > max_rows:
        # keep the most material strikes by |exposure|
        rows = sorted(rows, key=lambda kv: abs(kv[1]), reverse=True)[:max_rows]
        rows.sort()
    from datetime import UTC, datetime

    mp = max_pain_strike(splits)
    footer = (f"rendered {datetime.now(UTC).strftime('%H:%M UTC')} · "
              f"{norm.get('source', 'chain')} · {len(rows)} strikes"
              + (f" · max pain {mp:g}" if mp else ""))
    return _render(rows, ticker=norm["ticker"], spot=norm["spot"], kind="GEX",
                   king_strike=norm.get("king_strike"), flip=norm.get("flip"),
                   regime=norm.get("regime", "?"), sub="dealer gamma exposure",
                   splits=splits, cumulative=True, max_pain=mp, footer=footer)


def render_vex_png(norm: dict[str, Any] | None, *, max_rows: int = 60) -> bytes | None:
    """Render normalized VEX rows to PNG. None when unusable."""
    if not norm:
        return None
    rows = norm["strikes"]
    if len(rows) > max_rows:
        rows = sorted(rows, key=lambda kv: abs(kv[1]), reverse=True)[:max_rows]
        rows.sort()
    return _render(rows, ticker=norm.get("ticker", "?"), spot=norm["spot"], kind="VEX",
                   king_strike=None, flip=None,
                   regime="vol exposure", sub="dealer vomma exposure")


def walls_text(norm: dict[str, Any] | None) -> str:
    """Solstice walls readout from normalized GEX rows."""
    if not norm or not norm["strikes"]:
        return "walls unavailable — no exposure data."
    calls = [(k, g) for k, g in norm["strikes"] if g > 0]
    puts = [(k, g) for k, g in norm["strikes"] if g < 0]
    cw = max(calls, key=lambda kv: kv[1])[0] if calls else None
    pw = max(puts, key=lambda kv: abs(kv[1]))[0] if puts else None
    parts = [f"**{norm['ticker']}** spot {norm['spot']:.2f} · regime {norm.get('regime', '?')}"]
    if cw is not None:
        parts.append(f"Call wall (resistance): {cw:g}")
    if pw is not None:
        parts.append(f"Put wall (support): {pw:g}")
    if norm.get("flip"):
        side = "above" if norm["spot"] > norm["flip"] else "below"
        parts.append(f"Gamma flip: {norm['flip']:g} (spot {side})")
    if norm.get("king_strike"):
        parts.append(f"King Node (pin magnet): {norm['king_strike']:g}")
    net = sum(g for _, g in norm["strikes"])
    parts.append(f"Net GEX: {_fmt_money(net)}")
    mp = max_pain_strike(norm.get("splits") if isinstance(norm.get("splits"), dict) else None)
    if mp:
        parts.append(f"Max pain: {mp:g}")
    return "\n".join(parts)


async def get_heatmap_data(ticker: str) -> dict[str, Any] | None:
    """Normalized GEX rows via server.build_heatmap. None on failure."""
    try:
        import server

        payload = await server.build_heatmap(ticker.upper(), max_expiries=4)
        return gex_rows_from_heatmap(payload)
    except Exception as e:
        log.warning("heatmap data unavailable for %s: %s", ticker, e)
        return None


async def get_vex_data(ticker: str) -> dict[str, Any] | None:
    """Normalized VEX rows via paid chain + BS vomma. None on failure."""
    try:
        from services.public_api_adapter import fetch_chain_from_public_api

        chain = await fetch_chain_from_public_api(ticker.upper(), max_expiries=4)
        if not chain:
            return None
        out = vex_rows_from_contracts(chain.get("contracts", []),
                                      float(chain.get("spot") or 0))
        if out is not None:
            out["ticker"] = ticker.upper()
        return out
    except Exception as e:
        log.warning("vex data unavailable for %s: %s", ticker, e)
        return None
