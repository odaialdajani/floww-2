"""
backend/services/dash_ui.py

Dash/Plotly UI for the Confluence Decoder terminal.
Mounts into the existing FastAPI server at /dashboard/.

Tabs:
  1. Heatseeker — GEX heatmap with King Nodes, Air Pockets, Zero Gamma
  2. Flowseeker — Live options flow ticker with color coding
  3. Toxicity — VPIN, Quote Imbalance, Market Fragility gauges
  4. Vol Surface — 3D IV surface with SABR/SVI
  5. Trinity — Multi-ticker alignment and node lifecycle
  6. Atlas — Candlestick chart with overlays (King Nodes, ZG, Air Pockets, Anomaly, Trinity)
  7. Replay — Historical replay mode with play/pause/speed controls
  8. Agent Hub — YAML-defined trading agent archetypes
  9. Nexus — Social trading scaffold (leaderboard, comments)
"""
from __future__ import annotations

import functools
import json
import logging
import math
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

try:
    import dash
    from dash import dcc, html, Input, Output, State, callback, clientside_callback
    import dash_bootstrap_components as dbc
    HAS_DASH = True
except ImportError:
    try:
        from dash import dcc, html, Input, Output, State, callback, clientside_callback
        HAS_DASH = True
    except ImportError:
        HAS_DASH = False
        logger.warning("Dash not available — UI will not be mounted")

# ── Color constants ──────────────────────────────────────────────────────────
BG_DARK = "#0a0a1a"
BG_CARD = "#1a1a2e"
BG_PLOT = "#16213e"
ACCENT = "#00ff88"
WARN = "#ffaa00"
DANGER = "#ff4444"
TEXT = "#e0e0e0"
TEXT_DIM = "#888888"

# Light theme colors
BG_DARK_LIGHT = "#f5f5f5"
BG_CARD_LIGHT = "#ffffff"
BG_PLOT_LIGHT = "#fafafa"
TEXT_LIGHT = "#333333"
TEXT_DIM_LIGHT = "#666666"


def _empty_figure(title: str = "Waiting for data...", dark: bool = True) -> go.Figure:
    bg = BG_CARD if dark else BG_CARD_LIGHT
    plot = BG_PLOT if dark else BG_PLOT_LIGHT
    dim = TEXT_DIM if dark else TEXT_DIM_LIGHT
    fig = go.Figure()
    fig.add_annotation(
        text=title, xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=16, color=dim),
    )
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=bg, plot_bgcolor=plot,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def _error_figure(msg: str, dark: bool = True) -> go.Figure:
    bg = BG_CARD if dark else BG_CARD_LIGHT
    plot = BG_PLOT if dark else BG_PLOT_LIGHT
    fig = go.Figure()
    fig.add_annotation(
        text=f"Error: {msg}", xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(size=14, color=DANGER),
    )
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor=bg, plot_bgcolor=plot,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# I-8: Safe JSON helpers for dcc.Store persistence
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_json_value(val: Any) -> Any:
    """Guard against None / NaN / Inf in stored state. I-8 compliance."""
    if val is None:
        return None
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
    return val


def _sanitize_state_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize a state dict: replace None/NaN/Inf with safe defaults."""
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        safe = _safe_json_value(v)
        if safe is not None:
            out[k] = safe
    return out


def _default_toggle_state() -> Dict[str, Any]:
    """Default toggle state for Heatseeker sidebar."""
    return {
        "view": "GEX",
        "mode": "absolute",
        "indicators": [],       # visible overlay IDs
        "dte_min": 0,
        "dte_max": 365,
        "expiries": [],         # selected expiry dates (empty = all)
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HEATSEEKER TOGGLE COMPONENTS (sidebar injected into tab content)
# ═══════════════════════════════════════════════════════════════════════════════

def _overlay_options() -> List[Dict[str, str]]:
    """Available indicator overlay toggles."""
    return [
        {"label": "King Nodes", "value": "king_nodes"},
        {"label": "Air Pockets", "value": "air_pockets"},
        {"label": "Flip Zones", "value": "flip_zones"},
    ]


def _build_heatseeker_toggles(expiry_dates: Optional[List[str]] = None) -> html.Div:
    """Build the Heatseeker sidebar with all 5 toggle controls."""
    expiries = expiry_dates or []
    return html.Div([
        html.H5("View Controls", style={"color": ACCENT, "marginBottom": "12px"}),

        # VIEW: GEX / VEX / Charm / Vanna
        html.Label("View:", style={"color": TEXT_DIM, "fontSize": "11px"}),
        dcc.RadioItems(
            id="heatseeker-view-toggle",
            options=[
                {"label": "GEX", "value": "GEX"},
                {"label": "VEX", "value": "VEX"},
                {"label": "Charm", "value": "Charm"},
                {"label": "Vanna", "value": "Vanna"},
            ],
            value="GEX",
            labelStyle={"display": "inline-block", "marginRight": "10px", "color": TEXT, "fontSize": "11px"},
            inputStyle={"marginRight": "4px"},
        ),
        html.Br(),

        # MODE: absolute vs signed
        html.Label("Mode:", style={"color": TEXT_DIM, "fontSize": "11px"}),
        dcc.RadioItems(
            id="heatseeker-mode-toggle",
            options=[
                {"label": "Absolute", "value": "absolute"},
                {"label": "Signed", "value": "signed"},
            ],
            value="absolute",
            labelStyle={"display": "inline-block", "marginRight": "10px", "color": TEXT, "fontSize": "11px"},
            inputStyle={"marginRight": "4px"},
        ),
        html.Br(),

        # INDICATOR: King Nodes / Air Pockets / Flip Zones
        html.Label("Indicators:", style={"color": TEXT_DIM, "fontSize": "11px"}),
        dcc.Checklist(
            id="heatseeker-indicator-toggle",
            options=_overlay_options(),
            value=[],
            labelStyle={"display": "block", "color": TEXT, "fontSize": "11px"},
            inputStyle={"marginRight": "4px"},
        ),
        html.Br(),

        # DTE range filter
        html.Label("DTE Range:", style={"color": TEXT_DIM, "fontSize": "11px"}),
        dcc.RangeSlider(
            id="heatseeker-dte-toggle",
            min=0, max=365, step=1,
            value=[0, 365],
            marks={0: "0", 30: "30", 90: "90", 180: "180", 365: "365"},
            allowCross=False,
            tooltip={"placement": "bottom", "always_visible": False},
            updatemode="mouseup",
        ),
        html.Br(),

        # EXPIRIES multi-select
        html.Label("Expiries:", style={"color": TEXT_DIM, "fontSize": "11px"}),
        dcc.Dropdown(
            id="heatseeker-expiries-toggle",
            options=[{"label": e, "value": e} for e in expiries],
            value=[],
            multi=True,
            placeholder="All expiries",
            style={"backgroundColor": BG_CARD, "color": TEXT, "fontSize": "11px"},
            debounce=True,
        ),

        # Hidden: persist toggle state across re-renders
        dcc.Store(id="heatseeker-toggle-state", data=_default_toggle_state()),

    ], style={
        "padding": "12px", "backgroundColor": BG_CARD, "borderRadius": "4px",
        "minWidth": "180px", "marginRight": "10px",
    })


# ── Right-sidebar compute helpers (I-5/I-8 NaN-safe) ─────────────
def _compute_gamma_regime(contracts):
    """Return (label, dot_color, signed_ratio)."""
    if not contracts:
        return ("UNKNOWN", "#666666", 0.0)
    valid = [c.get("gex", 0) for c in contracts
             if isinstance(c.get("gex"), (int, float)) and math.isfinite(c.get("gex"))]
    net = sum(valid)
    total_abs = sum(abs(v) for v in valid)
    if total_abs <= 0:
        return ("UNKNOWN", "#666666", 0.0)
    ratio = net / total_abs
    if ratio > 0.10:
        return ("BULLISH", "#00ff88", ratio)
    if ratio < -0.10:
        return ("BEARISH", "#ff4444", ratio)
    return ("NEUTRAL", "#ffaa00", ratio)


def _compute_key_levels(spot, contracts):
    """Return {gamma_flip, call_wall, put_wall, max_pain, spot}."""
    out = {"gamma_flip": None, "call_wall": None, "put_wall": None,
           "max_pain": None, "spot": spot}
    if not contracts:
        return out
    by_strike = {}
    for c in contracts:
        s = c.get("strike")
        if not isinstance(s, (int, float)) or not math.isfinite(s):
            continue
        d = by_strike.setdefault(s, {"gex": 0.0, "call_oi": 0, "put_oi": 0})
        g = c.get("gex", 0)
        if isinstance(g, (int, float)) and math.isfinite(g):
            d["gex"] += g
        oi = c.get("oi", 0) or 0
        if c.get("type") == "call":
            d["call_oi"] += oi
        else:
            d["put_oi"] += oi
    strikes_sorted = sorted(by_strike.keys())
    # Gamma flip: where cumulative GEX crosses zero
    cum, prev_s = 0.0, None
    for s in strikes_sorted:
        cum_new = cum + by_strike[s]["gex"]
        if prev_s is not None and cum * cum_new < 0:
            out["gamma_flip"] = round((prev_s + s) / 2, 2)
            break
        cum, prev_s = cum_new, s
    # Walls
    calls_above = [(s, by_strike[s]["call_oi"]) for s in strikes_sorted if s > spot]
    if calls_above:
        out["call_wall"] = max(calls_above, key=lambda x: x[1])[0]
    puts_below = [(s, by_strike[s]["put_oi"]) for s in strikes_sorted if s < spot]
    if puts_below:
        out["put_wall"] = max(puts_below, key=lambda x: x[1])[0]
    # Max pain
    def pain_at(K):
        p = 0.0
        for s in strikes_sorted:
            if s >= K:
                p += by_strike[s]["call_oi"] * (s - K) * 100
            if s <= K:
                p += by_strike[s]["put_oi"] * (K - s) * 100
        return p
    if strikes_sorted:
        out["max_pain"] = min(strikes_sorted, key=pain_at)
    return out


def _compute_risk_levels(spot, contracts):
    """Return {R1, R2, S1, S2}. TODO: derive from ATR or IV instead of ±0.5%/1.0%."""
    if not spot or not math.isfinite(spot):
        return {"R1": None, "R2": None, "S1": None, "S2": None}
    return {
        "R1": round(spot * 1.005, 2),
        "R2": round(spot * 1.010, 2),
        "S1": round(spot * 0.995, 2),
        "S2": round(spot * 0.990, 2),
    }


def _compute_flip_zones(spot, contracts):
    """Return [(label, strike, pct_distance), ...]."""
    if not contracts or not spot:
        return []
    klv = _compute_key_levels(spot, contracts)
    zones = []
    for label, val in [("GEX Flip", klv["gamma_flip"]),
                       ("Max Pain", klv["max_pain"])]:
        if val is not None and math.isfinite(val):
            zones.append((label, val, (val - spot) / spot * 100))
    return zones


def _compute_stacked_nodes(contracts, top_n=4):
    """Return top N strikes by combined OI with call/put share."""
    if not contracts:
        return []
    by_strike = {}
    for c in contracts:
        s = c.get("strike")
        if not isinstance(s, (int, float)) or not math.isfinite(s):
            continue
        d = by_strike.setdefault(s, {"call_oi": 0, "put_oi": 0})
        oi = c.get("oi", 0) or 0
        if c.get("type") == "call":
            d["call_oi"] += oi
        else:
            d["put_oi"] += oi
    nodes = []
    for s, d in by_strike.items():
        total = d["call_oi"] + d["put_oi"]
        if total > 0:
            nodes.append({
                "strike": s,
                "call_pct": d["call_oi"] / total * 100,
                "put_pct":  d["put_oi"]  / total * 100,
                "total_oi": total,
            })
    nodes.sort(key=lambda n: n["total_oi"], reverse=True)
    return nodes[:top_n]


def _compute_tug_of_war(contracts):
    """Return (positive_gex_total, negative_gex_total) in dollars."""
    if not contracts:
        return (0.0, 0.0)
    valid = [c.get("gex", 0) for c in contracts
             if isinstance(c.get("gex"), (int, float)) and math.isfinite(c.get("gex"))]
    return (sum(v for v in valid if v > 0), sum(v for v in valid if v < 0))


def _compute_cell_tags(spot, contracts):
    """Return {strike: [tag_labels]} for KING/FLOOR/CEIL/GATE/AIR."""
    if not contracts:
        return {}
    by_strike = {}
    for c in contracts:
        s = c.get("strike")
        if not isinstance(s, (int, float)) or not math.isfinite(s):
            continue
        g = c.get("gex", 0)
        if isinstance(g, (int, float)) and math.isfinite(g):
            by_strike.setdefault(s, 0.0)
            by_strike[s] += g
    if not by_strike:
        return {}
    total_abs = sum(abs(g) for g in by_strike.values())
    if total_abs <= 0:
        return {}
    tags = {s: [] for s in by_strike}
    king = max(by_strike, key=lambda s: abs(by_strike[s]))
    tags[king].append("KING")
    for s in sorted([k for k in by_strike if by_strike[k] > 0 and k <= spot],
                    key=lambda s: by_strike[s], reverse=True)[:3]:
        tags[s].append("FLOOR")
    for s in sorted([k for k in by_strike if by_strike[k] < 0 and k >= spot],
                    key=lambda s: by_strike[s])[:3]:
        tags[s].append("CEIL")
    for s, g in by_strike.items():
        if abs(g) / total_abs > 0.10 and "KING" not in tags[s]:
            tags[s].append("GATE")
    for s, g in by_strike.items():
        if abs(g) / total_abs < 0.01:
            tags[s].append("AIR")
    return {s: t for s, t in tags.items() if t}


def _fmt_money(n):
    """Format dollar amounts: $1.50B, $473.2M, $52.3K, or '—'."""
    if not isinstance(n, (int, float)) or not math.isfinite(n):
        return "—"
    if abs(n) >= 1e9:
        return f"${n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"${n/1e6:.1f}M"
    if abs(n) >= 1e3:
        return f"${n/1e3:.1f}K"
    return f"${n:.0f}"

@functools.lru_cache(maxsize=32)
def _cached_build_heatmap(
    view: str,
    mode: str,
    spot: float,
    gex_surface_json: str,
    strikes_json: str,
    expiries_json: str,
    king_nodes_json: str,
    air_pockets_json: str,
    zero_gamma: float,
    indicators_json: str,
) -> go.Figure:
    """Memoized heatmap builder. Accepts JSON-serializable args for cacheability."""
    gex_surface = json.loads(gex_surface_json) if gex_surface_json else None
    strikes = json.loads(strikes_json) if strikes_json else None
    expiries_list = json.loads(expiries_json) if expiries_json else None
    king_nodes = json.loads(king_nodes_json) if king_nodes_json else None
    air_pockets = json.loads(air_pockets_json) if air_pockets_json else None
    indicators = json.loads(indicators_json) if indicators_json else []

    # Route to the appropriate builder based on view type
    if view == "GEX":
        return _build_gex_heatmap(
            spot=spot, gex_surface=gex_surface, strikes=strikes,
            expiries=expiries_list,
            king_nodes=king_nodes if "king_nodes" in indicators else None,
            air_pockets=air_pockets if "air_pockets" in indicators else None,
            zero_gamma=zero_gamma, dark=True,
            mode=mode,
        )
    elif view == "VEX":
        return _build_vex_heatmap(
            spot=spot, contracts=None,
            gex_surface=gex_surface, strikes=strikes,
            expiries=expiries_list,
            king_nodes=king_nodes if "king_nodes" in indicators else None,
            air_pockets=air_pockets if "air_pockets" in indicators else None,
            zero_gamma=zero_gamma, dark=True,
            mode=mode,
        )
    elif view == "Charm":
        return _build_charm_heatmap(
            spot=spot, contracts=None,
            gex_surface=gex_surface, strikes=strikes,
            expiries=expiries_list,
            king_nodes=king_nodes if "king_nodes" in indicators else None,
            air_pockets=air_pockets if "air_pockets" in indicators else None,
            zero_gamma=zero_gamma, dark=True,
            mode=mode,
        )
    elif view == "Vanna":
        return _build_vanna_heatmap(
            spot=spot, contracts=None,
            gex_surface=gex_surface, strikes=strikes,
            expiries=expiries_list,
            king_nodes=king_nodes if "king_nodes" in indicators else None,
            air_pockets=air_pockets if "air_pockets" in indicators else None,
            zero_gamma=zero_gamma, dark=True,
            mode=mode,
        )
    # Fallback
    return _build_gex_heatmap(
        spot=spot, gex_surface=gex_surface, strikes=strikes,
        expiries=expiries_list,
        king_nodes=king_nodes if "king_nodes" in indicators else None,
        air_pockets=air_pockets if "air_pockets" in indicators else None,
        zero_gamma=zero_gamma, dark=True,
        mode=mode,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# VARIANT HEATMAP BUILDERS (VEX / Charm / Vanna views)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_vex_heatmap(
    spot: float = 0,
    contracts: Optional[List[Dict]] = None,
    gex_surface: Optional[List[List[float]]] = None,
    strikes: Optional[List[float]] = None,
    expiries: Optional[List[float]] = None,
    king_nodes: Optional[List[Dict]] = None,
    air_pockets: Optional[List[Dict]] = None,
    zero_gamma: Optional[float] = None,
    dark: bool = True,
    mode: str = "absolute",
) -> go.Figure:
    """Build VEX (vanna exposure) heatmap. Reuses GEX structure with alternate colorscale."""
    fig = _build_gex_heatmap(
        spot=spot, contracts=contracts, gex_surface=gex_surface,
        strikes=strikes, expiries=expiries, king_nodes=king_nodes,
        air_pockets=air_pockets, zero_gamma=zero_gamma, dark=dark,
        mode=mode,
    )
    if fig.data:
        fig.data[0].colorscale = [[0.0, "#7c3aed"], [0.25, "#a78bfa"], [0.5, "#c4b5fd"],
                                   [0.5, "#e0e0e0"], [0.5, "#93c5fd"], [0.75, "#3b82f6"], [1.0, "#1e40af"]]
        fig.layout.title.text = "VEX Heatseeker"
    return fig


def _build_charm_heatmap(
    spot: float = 0,
    contracts: Optional[List[Dict]] = None,
    gex_surface: Optional[List[float]] = None,
    strikes: Optional[List[float]] = None,
    expiries: Optional[List[float]] = None,
    king_nodes: Optional[List[Dict]] = None,
    air_pockets: Optional[List[Dict]] = None,
    zero_gamma: Optional[float] = None,
    dark: bool = True,
    mode: str = "absolute",
) -> go.Figure:
    """Build Charm (delta decay) heatmap. Reuses GEX structure with warm colorscale."""
    fig = _build_gex_heatmap(
        spot=spot, contracts=contracts, gex_surface=gex_surface,
        strikes=strikes, expiries=expiries, king_nodes=king_nodes,
        air_pockets=air_pockets, zero_gamma=zero_gamma, dark=dark,
        mode=mode,
    )
    if fig.data:
        fig.data[0].colorscale = [[0.0, "#b45309"], [0.25, "#f59e0b"], [0.5, "#fde68a"],
                                   [0.5, "#e0e0e0"], [0.5, "#a7f3d0"], [0.75, "#34d399"], [1.0, "#059669"]]
        fig.layout.title.text = "Charm Heatseeker"
    return fig


def _build_vanna_heatmap(
    spot: float = 0,
    contracts: Optional[List[Dict]] = None,
    gex_surface: Optional[List[float]] = None,
    strikes: Optional[List[float]] = None,
    expiries: Optional[List[float]] = None,
    king_nodes: Optional[List[Dict]] = None,
    air_pockets: Optional[List[Dict]] = None,
    zero_gamma: Optional[float] = None,
    dark: bool = True,
    mode: str = "absolute",
) -> go.Figure:
    """Build Vanna (delta sensitivity to vol) heatmap. Reuses GEX structure with cool colorscale."""
    fig = _build_gex_heatmap(
        spot=spot, contracts=contracts, gex_surface=gex_surface,
        strikes=strikes, expiries=expiries, king_nodes=king_nodes,
        air_pockets=air_pockets, zero_gamma=zero_gamma, dark=dark,
        mode=mode,
    )
    if fig.data:
        fig.data[0].colorscale = [[0.0, "#dc2626"], [0.25, "#f87171"], [0.5, "#fca5a5"],
                                   [0.5, "#e0e0e0"], [0.5, "#67e8f9"], [0.75, "#22d3ee"], [1.0, "#0891b2"]]
        fig.layout.title.text = "Vanna Heatseeker"
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: HEATSEEKER — GEX Heatmap with Overlays
# ═══════════════════════════════════════════════════════════════════════════════

def _build_gex_heatmap(
    spot: float = 0,
    contracts: Optional[List[Dict]] = None,
    gex_surface: Optional[List[List[float]]] = None,
    strikes: Optional[List[float]] = None,
    expiries: Optional[List[float]] = None,
    king_nodes: Optional[List[Dict]] = None,
    air_pockets: Optional[List[Dict]] = None,
    zero_gamma: Optional[float] = None,
    dark: bool = True,
    mode: str = "absolute",
) -> go.Figure:
    """Build GEX heatmap: strikes x time, with overlays.

    mode="absolute"  → |GEX| (all positive, magnitude only)
    mode="signed"    → signed GEX (positive = dealer long, negative = dealer short)
    """
    if not contracts and gex_surface is None:
        return _empty_figure("Waiting for GEX data...", dark)

    try:
        if gex_surface is not None and strikes and expiries:
            z = gex_surface
            y_labels = [f"{s:.1f}" for s in strikes]
            x_labels = [f"T={t:.3f}" for t in expiries]
        elif spot > 0 and contracts:
            try:
                from services.gex_aggregator import GexAggregator
                agg = GexAggregator()
                result = agg.compute(spot, contracts)
                strikes = result.get("strikes", [])
                expiries = result.get("expiries", [])
                z = result.get("gex_surface", [])
                if not z or not strikes or not expiries:
                    return _empty_figure("No GEX surface data available", dark)
                y_labels = [f"{s:.1f}" for s in strikes]
                x_labels = [f"T={t:.3f}" for t in expiries]
            except Exception as e:
                logger.error(f"GEX aggregator error: {e}")
                return _error_figure(f"GEX error: {e}", dark)
        else:
            return _empty_figure("Waiting for GEX data...", dark)

        tpl = "plotly_dark" if dark else "plotly_white"
        bg = BG_CARD if dark else BG_CARD_LIGHT
        plot = BG_PLOT if dark else BG_PLOT_LIGHT
        accent = ACCENT if dark else "#00aa55"

        # MODE: absolute vs signed
        if mode == "absolute":
            z = [[abs(val) for val in row] for row in z]
            zmid_mode = None
            cbar_title = "|GEX| ($)"
        else:
            zmid_mode = 0
            cbar_title = "GEX ($)"

        fig = go.Figure()
        fig.add_trace(go.Heatmap(
            z=z, x=x_labels, y=y_labels,
            colorscale=[[0.0, "#d73027"], [0.25, "#fc8d59"], [0.45, "#fee090"],
                        [0.50, "#ffffbf"], [0.55, "#e0f3f8"], [0.75, "#91bfdb"], [1.0, "#4575b4"]],
            zmid=zmid_mode, colorbar=dict(title=cbar_title, x=1.02, thickness=15),
            hovertemplate="Strike: %{y}<br>TTE: %{x}<br>GEX: %{z:,.0f}<extra></extra>",
        ))

        if spot > 0 and strikes:
            closest_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
            fig.add_hline(y=y_labels[closest_idx], line_dash="dash", line_color=accent, line_width=2)
            fig.add_annotation(x=x_labels[-1] if x_labels else 0, y=y_labels[closest_idx],
                text=f"Spot {spot:.2f}", showarrow=False, font=dict(color=accent, size=11),
                xanchor="right", yanchor="bottom")

        if zero_gamma is not None and zero_gamma > 0 and strikes:
            zg_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - zero_gamma))
            fig.add_hline(y=y_labels[zg_idx], line_dash="dot", line_color="#ff00ff", line_width=2)
            fig.add_annotation(x=x_labels[-1] if x_labels else 0, y=y_labels[zg_idx],
                text=f"ZG {zero_gamma:.1f}", showarrow=False, font=dict(color="#ff00ff", size=10),
                xanchor="right", yanchor="top")

        if king_nodes:
            for kn in king_nodes[:3]:
                sv = kn.get("strike", 0)
                mag = kn.get("magnitude", 0)
                if sv > 0 and strikes:
                    kn_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - sv))
                    fig.add_hline(y=y_labels[kn_idx], line_dash="solid", line_color="#ff00ff",
                                  line_width=1.5, opacity=0.7)
                    fig.add_annotation(x=x_labels[-1] if x_labels else 0, y=y_labels[kn_idx],
                        text=f"KN {sv:.0f} ({mag:,.0f})", showarrow=False,
                        font=dict(size=10, color="#ff00ff"), xanchor="right", yanchor="middle")

        if air_pockets:
            for ap in air_pockets:
                lo, hi = ap.get("lo", 0), ap.get("hi", 0)
                if lo < hi:
                    fig.add_hrect(y0=lo, y1=hi, fillcolor="rgba(255,255,0,0.08)", line_width=0, layer="below")

        fig.update_layout(
            title=dict(text="GEX Heatseeker", font=dict(color=TEXT if dark else TEXT_LIGHT, size=18)),
            xaxis_title="Time to Expiry (years)", yaxis_title="Strike ($)",
            template=tpl, paper_bgcolor=bg, plot_bgcolor=plot, height=650,
            margin=dict(l=60, r=80, t=60, b=40),
        )
        return fig
    except Exception as e:
        logger.error(f"GEX heatmap error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: FLOWSEEKER — Live Options Flow Ticker
# ═══════════════════════════════════════════════════════════════════════════════

def _classify_row_color(size: float, daily_volume: float, oi: float, classification: str) -> str:
    if size > daily_volume or size > oi:
        return "rgba(255,68,68,0.25)"
    if classification and classification.lower() == "sweep":
        return "rgba(255,170,0,0.20)"
    return "rgba(26,26,46,0)"


def _build_flow_ticker(flow_data: Optional[List[Dict]] = None, dark: bool = True) -> go.Figure:
    if not flow_data:
        return _empty_figure("Waiting for flow data...", dark)
    try:
        sorted_data = sorted(flow_data, key=lambda p: p.get("timestamp", ""), reverse=True)[:100]
        timestamps = [p.get("timestamp", "")[:19] for p in sorted_data]
        tickers = [p.get("ticker", "") for p in sorted_data]
        strikes = [f"{p.get('strike', 0):.1f}" for p in sorted_data]
        expiries = [p.get("expiration", p.get("expiry", "")) for p in sorted_data]
        sides = [p.get("side", "") for p in sorted_data]
        types_ = [p.get("type", "") for p in sorted_data]
        sizes = [f"{p.get('size', 0):,}" for p in sorted_data]
        premiums = [f"${p.get('premium', p.get('notional', 0)):,.0f}" for p in sorted_data]
        vol_oi = [f"{p.get('vol_oi_ratio', 0):.2f}" for p in sorted_data]
        classifications = [p.get("classification", "") for p in sorted_data]

        row_colors = []
        for p in sorted_data:
            sz = p.get("size", 0)
            dv = p.get("daily_volume", sz + 1)
            oi = p.get("open_interest", sz + 1)
            cl = p.get("classification", "")
            row_colors.append(_classify_row_color(sz, dv, oi, cl))

        fill_colors = [[row_colors[i] for i in range(len(sorted_data))] for _ in range(10)]
        bg = BG_CARD if dark else BG_CARD_LIGHT

        fig = go.Figure(data=[go.Table(
            header=dict(
                values=["Time", "Ticker", "Strike", "Expiry", "Side", "Type", "Size", "Premium", "Vol/OI", "Class"],
                fill_color="#0f3460", font=dict(color=TEXT, size=11, family="monospace"),
                align="left", height=32, line=dict(color="#333", width=1),
            ),
            cells=dict(
                values=[timestamps, tickers, strikes, expiries, sides, types_, sizes, premiums, vol_oi, classifications],
                fill_color=fill_colors, font=dict(color="#ccc" if dark else "#333", size=10, family="monospace"),
                align="left", height=26, line=dict(color="#222" if dark else "#ddd", width=0.5),
            ),
        )])
        tpl = "plotly_dark" if dark else "plotly_white"
        fig.update_layout(
            title=dict(text="Flowseeker — Live Options Flow", font=dict(color=TEXT if dark else TEXT_LIGHT, size=18)),
            template=tpl, paper_bgcolor=bg, margin=dict(l=10, r=10, t=50, b=10), height=650,
        )
        return fig
    except Exception as e:
        logger.error(f"Flow ticker error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: TOXICITY & LIQUIDITY
# ═══════════════════════════════════════════════════════════════════════════════

def _build_toxicity_dashboard(
    vpin_cdf: float = 0, qi_zscore: float = 0, fragility_score: float = 0,
    retail_flow_score: float = 0,
    regime: str = "NORMAL", history_vpin: Optional[List[float]] = None,
    history_qi: Optional[List[float]] = None, history_ts: Optional[List[str]] = None,
    dark: bool = True,
) -> go.Figure:
    try:
        is_toxic = vpin_cdf > 0.5 and abs(qi_zscore) > 1.5
        tpl = "plotly_dark" if dark else "plotly_white"
        bg = BG_CARD if dark else BG_CARD_LIGHT
        plot = BG_PLOT if dark else BG_PLOT_LIGHT
        text_color = TEXT if dark else TEXT_LIGHT
        dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

        fig = make_subplots(
            rows=4, cols=2,
            specs=[[{"type": "indicator"}, {"type": "indicator"}],
                   [{"type": "indicator", "colspan": 2}, None],
                   [{"type": "indicator", "colspan": 2}, None],
                   [{"type": "scatter", "colspan": 2}, None]],
            subplot_titles=[
                "VPIN CDF", "Quote Imbalance Z-Score", "Market Fragility Index",
                "Retail Flow Score", "60-min History",
            ],
            vertical_spacing=0.06, row_heights=[0.2, 0.2, 0.2, 0.4],
        )
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=vpin_cdf * 100,
            number={"suffix": "%", "font": {"color": text_color, "size": 20}},
            gauge={"axis": {"range": [0, 100], "tickcolor": dim},
                   "bar": {"color": DANGER if vpin_cdf > 0.5 else ACCENT},
                   "bgcolor": plot,
                   "steps": [{"range": [0, 50], "color": "rgba(0,255,136,0.08)"},
                             {"range": [50, 75], "color": "rgba(255,170,0,0.12)"},
                             {"range": [75, 100], "color": "rgba(255,68,68,0.15)"}],
                   "threshold": {"line": {"color": DANGER, "width": 3}, "value": 50}},
        ), row=1, col=1)

        qi_color = DANGER if abs(qi_zscore) > 1.5 else WARN if abs(qi_zscore) > 1.0 else ACCENT
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=qi_zscore,
            number={"prefix": "z=", "font": {"color": text_color, "size": 20}},
            gauge={"axis": {"range": [-5, 5], "tickcolor": dim}, "bar": {"color": qi_color},
                   "bgcolor": plot,
                   "steps": [{"range": [-5, -1.5], "color": "rgba(255,68,68,0.1)"},
                             {"range": [-1.5, 1.5], "color": "rgba(0,255,136,0.05)"},
                             {"range": [1.5, 5], "color": "rgba(255,68,68,0.1)"}]},
        ), row=1, col=2)

        frag_color = DANGER if fragility_score > 66 else WARN if fragility_score > 33 else ACCENT
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=fragility_score,
            number={"suffix": "/100", "font": {"color": text_color, "size": 18}},
            gauge={"axis": {"range": [0, 100], "tickcolor": dim}, "bar": {"color": frag_color},
                   "bgcolor": plot,
                   "steps": [{"range": [0, 33], "color": "rgba(0,255,136,0.08)"},
                             {"range": [33, 66], "color": "rgba(255,170,0,0.1)"},
                             {"range": [66, 100], "color": "rgba(255,68,68,0.15)"}]},
        ), row=2, col=1)

        # Retail Flow Score gauge (-100 to +100)
        rfs = retail_flow_score
        if rfs >= 30:
            rfs_color = ACCENT
        elif rfs <= -30:
            rfs_color = DANGER
        else:
            rfs_color = WARN
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=rfs,
            number={"font": {"color": text_color, "size": 18}},
            gauge={"axis": {"range": [-100, 100], "tickcolor": dim},
                   "bar": {"color": rfs_color},
                   "bgcolor": plot,
                   "steps": [{"range": [-100, -30], "color": "rgba(255,68,68,0.1)"},
                             {"range": [-30, 30], "color": "rgba(255,170,0,0.06)"},
                             {"range": [30, 100], "color": "rgba(0,255,136,0.08)"}],
                   "threshold": {"line": {"color": WARN, "width": 2}, "value": 0}},
        ), row=3, col=1)

        if history_vpin and history_ts:
            fig.add_trace(go.Scatter(x=history_ts, y=[v * 100 for v in history_vpin],
                mode="lines", name="VPIN CDF %", line=dict(color=DANGER, width=1.5)), row=4, col=1)
        if history_qi and history_ts:
            fig.add_trace(go.Scatter(x=history_ts, y=history_qi,
                mode="lines", name="QI Z-Score", line=dict(color=WARN, width=1.5)), row=4, col=1)

        if is_toxic:
            fig.add_annotation(xref="paper", yref="paper", x=0.5, y=1.08,
                text="TOXIC FLOW DETECTED", showarrow=False,
                font=dict(size=22, color=DANGER, family="monospace"),
                bgcolor="rgba(58,26,26,0.9)", bordercolor=DANGER, borderwidth=2, borderpad=10)
        else:
            fig.add_annotation(xref="paper", yref="paper", x=0.5, y=1.08,
                text=f"Regime: {regime}", showarrow=False,
                font=dict(size=14, color=dim, family="monospace"))

        fig.update_layout(
            title=dict(text="Toxicity & Retail Flow", font=dict(color=text_color, size=18)),
            template=tpl, paper_bgcolor=bg, plot_bgcolor=plot, height=900,
            showlegend=True, legend=dict(font=dict(color=dim, size=10)),
        )
        return fig
    except Exception as e:
        logger.error(f"Toxicity dashboard error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: VOL SURFACE — 3D SABR/SVI Surface
# ═══════════════════════════════════════════════════════════════════════════════

def _build_vol_surface(
    spot: float = 0, contracts: Optional[List[Dict]] = None, ticker: str = "SPY",
    grid_strikes: Optional[List[float]] = None, grid_expiries: Optional[List[float]] = None,
    iv_grid: Optional[List[List[float]]] = None, atm_skew: Optional[List[Dict]] = None,
    butterfly: Optional[List[Dict]] = None, dark: bool = True,
) -> go.Figure:
    try:
        if iv_grid is None or grid_strikes is None or grid_expiries is None:
            if spot > 0 and contracts:
                try:
                    from services.stochastic_vol import VolSurfaceConstructor
                    svc = VolSurfaceConstructor()
                    result = svc.build_surface(spot, contracts)
                    grid_strikes = result.get("grid_strikes", [])
                    grid_expiries = result.get("grid_expiries", [])
                    iv_grid = result.get("iv_grid", [])
                except Exception as e:
                    return _error_figure(f"Vol surface error: {e}", dark)
        if not iv_grid or not grid_strikes or not grid_expiries:
            return _empty_figure(f"Waiting for {ticker} vol surface data...", dark)

        tpl = "plotly_dark" if dark else "plotly_white"
        bg = BG_CARD if dark else BG_CARD_LIGHT
        plot = BG_PLOT if dark else BG_PLOT_LIGHT
        text_color = TEXT if dark else TEXT_LIGHT

        fig = make_subplots(
            rows=2, cols=1, row_heights=[0.65, 0.35],
            specs=[[{"type": "surface"}], [{"type": "scatter"}]],
            subplot_titles=["3D Implied Volatility Surface", "ATM Term Structure + 25d Skew"],
            vertical_spacing=0.12,
        )
        fig.add_trace(go.Surface(
            x=grid_strikes, y=grid_expiries, z=iv_grid, colorscale="Viridis",
            colorbar=dict(title="IV", x=1.02, thickness=15),
            hovertemplate="Strike: %{x:.1f}<br>TTE: %{y:.4f}<br>IV: %{z:.4f}<extra></extra>",
            lighting=dict(ambient=0.6, diffuse=0.8, roughness=0.4),
        ), row=1, col=1)

        if atm_skew:
            fig.add_trace(go.Scatter(
                x=[p.get("expiry", 0) for p in atm_skew], y=[p.get("atm_iv", 0) for p in atm_skew],
                mode="lines+markers", name="ATM IV", line=dict(color=ACCENT, width=2)), row=2, col=1)
        if butterfly:
            fig.add_trace(go.Scatter(
                x=[p.get("expiry", 0) for p in butterfly], y=[p.get("butterfly_25d", 0) for p in butterfly],
                mode="lines+markers", name="25d Butterfly", line=dict(color=WARN, width=1.5, dash="dash")), row=2, col=1)

        fig.update_layout(
            title=dict(text=f"Vol Surface — {ticker}", font=dict(color=text_color, size=18)),
            scene=dict(xaxis_title="Strike", yaxis_title="TTE", zaxis_title="Implied Vol",
                       bgcolor=plot, xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333"), zaxis=dict(gridcolor="#333")),
            template=tpl, paper_bgcolor=bg, height=800, showlegend=True,
            legend=dict(font=dict(color=TEXT_DIM if dark else TEXT_DIM_LIGHT, size=10)),
        )
        return fig
    except Exception as e:
        logger.error(f"Vol surface error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: TRINITY ALIGNMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _build_trinity_dashboard(
    score: float = 0, regime: str = "NONE",
    spy_zg: Optional[List[Dict]] = None, qqq_zg: Optional[List[Dict]] = None,
    spx_zg: Optional[List[Dict]] = None, cross_corr: Optional[List[List[float]]] = None,
    aligned_levels: Optional[List[Dict]] = None, dark: bool = True,
) -> go.Figure:
    try:
        tpl = "plotly_dark" if dark else "plotly_white"
        bg = BG_CARD if dark else BG_CARD_LIGHT
        plot = BG_PLOT if dark else BG_PLOT_LIGHT
        text_color = TEXT if dark else TEXT_LIGHT
        dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

        fig = make_subplots(
            rows=3, cols=2,
            specs=[[{"type": "indicator", "colspan": 2}, None],
                   [{"type": "scatter"}, {"type": "scatter"}],
                   [{"type": "scatter"}, {"type": "heatmap"}]],
            subplot_titles=["Trinity Alignment Score", "SPY Zero Gamma", "QQQ Zero Gamma", "SPX Zero Gamma", "Cross-Correlation"],
            vertical_spacing=0.1, row_heights=[0.25, 0.35, 0.4],
        )
        score_color = ACCENT if score >= 75 else WARN if score >= 50 else DANGER
        fig.add_trace(go.Indicator(
            mode="gauge+number", value=score, number={"suffix": "/100", "font": {"color": text_color, "size": 24}},
            gauge={"axis": {"range": [0, 100], "tickcolor": dim}, "bar": {"color": score_color}, "bgcolor": plot,
                   "steps": [{"range": [0, 25], "color": "rgba(255,68,68,0.1)"}, {"range": [25, 50], "color": "rgba(255,170,0,0.08)"},
                             {"range": [50, 75], "color": "rgba(0,255,136,0.05)"}, {"range": [75, 100], "color": "rgba(0,255,136,0.1)"}]},
        ), row=1, col=1)

        for col_idx, (data, name, color) in enumerate([(spy_zg, "SPY ZG", ACCENT), (qqq_zg, "QQQ ZG", "#4488ff")], start=1):
            if data:
                ts = [d.get("ts", "") for d in data]
                vals = [d.get("value", d.get("level", 0)) for d in data]
                fig.add_trace(go.Scatter(x=ts, y=vals, mode="lines", name=name, line=dict(color=color, width=1.5)), row=2, col=col_idx)

        if spx_zg:
            ts = [d.get("ts", "") for d in spx_zg]
            vals = [d.get("value", d.get("level", 0)) for d in spx_zg]
            fig.add_trace(go.Scatter(x=ts, y=vals, mode="lines", name="SPX ZG", line=dict(color="#ff44ff", width=1.5)), row=3, col=1)

        if cross_corr:
            fig.add_trace(go.Heatmap(z=cross_corr, x=["SPY", "QQQ", "SPX"], y=["SPY", "QQQ", "SPX"],
                colorscale="RdBu", zmid=0, text=[[f"{v:.2f}" for v in row] for row in cross_corr],
                texttemplate="%{text}", textfont=dict(size=12, color=text_color),
                colorbar=dict(title="corr", x=1.02)), row=3, col=2)

        fig.update_layout(
            title=dict(text="Trinity Alignment & Node Lifecycle", font=dict(color=text_color, size=18)),
            template=tpl, paper_bgcolor=bg, plot_bgcolor=plot, height=850, showlegend=True,
            legend=dict(font=dict(color=dim, size=10)),
        )
        return fig
    except Exception as e:
        logger.error(f"Trinity dashboard error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 6: ATLAS — Candlestick + Overlays
# ═══════════════════════════════════════════════════════════════════════════════

def _build_atlas_chart(
    ohlc_data: Optional[List[Dict]] = None,
    overlays: Optional[Dict[str, Any]] = None,
    time_window: str = "4h",
    dark: bool = True,
) -> go.Figure:
    """Build Atlas candlestick chart with toggleable overlays."""
    tpl = "plotly_dark" if dark else "plotly_white"
    bg = BG_CARD if dark else BG_CARD_LIGHT
    plot = BG_PLOT if dark else BG_PLOT_LIGHT
    text_color = TEXT if dark else TEXT_LIGHT

    try:
        if not ohlc_data:
            return _empty_figure("Waiting for candlestick data...<br>Select a ticker and time window", dark)

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=[d.get("timestamp", "") for d in ohlc_data],
            open=[d.get("open", 0) for d in ohlc_data],
            high=[d.get("high", 0) for d in ohlc_data],
            low=[d.get("low", 0) for d in ohlc_data],
            close=[d.get("close", 0) for d in ohlc_data],
            name="Price",
            increasing_line_color=ACCENT, decreasing_line_color=DANGER,
        ))

        if overlays:
            # King Node lines
            if overlays.get("show_king_nodes", True):
                for kn in (overlays.get("king_nodes") or [])[:3]:
                    sv = kn.get("strike", 0)
                    if sv > 0:
                        fig.add_hline(y=sv, line_dash="solid", line_color="#ff00ff",
                                      line_width=1.5, opacity=0.7)
                        fig.add_annotation(x=ohlc_data[-1].get("timestamp", "") if ohlc_data else 0, y=sv,
                            text=f"KN {sv:.0f}", showarrow=False, font=dict(size=9, color="#ff00ff"),
                            xanchor="right", yanchor="middle")

            # Zero Gamma line
            if overlays.get("show_zero_gamma", True):
                zg = overlays.get("zero_gamma")
                if zg and zg > 0:
                    fig.add_hline(y=zg, line_dash="dot", line_color="#ff00ff", line_width=2)
                    fig.add_annotation(x=ohlc_data[-1].get("timestamp", "") if ohlc_data else 0, y=zg,
                        text=f"ZG {zg:.1f}", showarrow=False, font=dict(size=10, color="#ff00ff"),
                        xanchor="right", yanchor="top")

            # Air Pockets
            if overlays.get("show_air_pockets", True):
                for ap in (overlays.get("air_pockets") or []):
                    lo, hi = ap.get("lo", 0), ap.get("hi", 0)
                    if lo < hi:
                        fig.add_hrect(y0=lo, y1=hi, fillcolor="rgba(255,255,0,0.06)", line_width=0, layer="below")

            # Anomaly markers
            if overlays.get("show_anomalies", True):
                for marker in (overlays.get("anomaly_markers") or []):
                    ts = marker.get("timestamp", "")
                    # Find closest candle
                    for d in ohlc_data:
                        if d.get("timestamp", "").startswith(ts[:16]):
                            fig.add_trace(go.Scatter(
                                x=[d.get("timestamp", "")], y=[d.get("high", 0) * 1.001],
                                mode="markers", marker=dict(symbol="triangle-down", size=10, color=DANGER),
                                name="Anomaly", showlegend=False,
                            ))
                            break

        fig.update_layout(
            title=dict(text=f"Atlas — Candlestick ({time_window})", font=dict(color=text_color, size=18)),
            xaxis_title="Time", yaxis_title="Price ($)",
            template=tpl, paper_bgcolor=bg, plot_bgcolor=plot, height=700,
            xaxis_rangeslider_visible=False,
            margin=dict(l=60, r=40, t=60, b=40),
        )
        return fig
    except Exception as e:
        logger.error(f"Atlas chart error: {e}")
        return _error_figure(str(e), dark)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 7: REPLAY — Historical Replay Mode
# ═══════════════════════════════════════════════════════════════════════════════

def _build_replay_controls(
    replay_status: Optional[Dict] = None, dark: bool = True,
) -> html.Div:
    """Build replay mode controls."""
    tpl = "plotly_dark" if dark else "plotly_white"
    bg = BG_CARD if dark else BG_CARD_LIGHT
    text_color = TEXT if dark else TEXT_LIGHT
    dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

    status = replay_status or {"running": False}
    is_running = status.get("running", False)

    return html.Div([
        html.Div([
            html.Label("Start:", style={"color": dim, "marginRight": "8px"}),
            dcc.Input(id="replay-start", type="text", placeholder="2026-05-20T09:30:00",
                      style={"width": "180px", "backgroundColor": plot, "color": text_color, "border": "11px solid #333"}),
            html.Label("End:", style={"color": dim, "marginLeft": "12px", "marginRight": "8px"}),
            dcc.Input(id="replay-end", type="text", placeholder="2026-05-20T10:30:00",
                      style={"width": "180px", "backgroundColor": plot, "color": text_color, "border": "1px solid #333"}),
            html.Label("Speed:", style={"color": dim, "marginLeft": "12px", "marginRight": "8px"}),
            dcc.Dropdown(id="replay-speed", options=[
                {"label": "1x", "value": "1"}, {"label": "10x", "value": "10"},
                {"label": "100x", "value": "100"}, {"label": "1000x", "value": "1000"},
            ], value="10", clearable=False, style={"width": "80px", "display": "inline-block"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "4px", "marginBottom": "10px"}),

        html.Div([
            html.Button("Play", id="replay-play-btn", n_clicks=0,
                        style={"backgroundColor": ACCENT, "color": "#000", "border": "none",
                               "padding": "6px 16px", "marginRight": "8px", "borderRadius": "4px", "cursor": "pointer"}),
            html.Button("Pause", id="replay-pause-btn", n_clicks=0,
                        style={"backgroundColor": WARN, "color": "#000", "border": "none",
                               "padding": "6px 16px", "marginRight": "8px", "borderRadius": "4px", "cursor": "pointer"}),
            html.Button("Stop", id="replay-stop-btn", n_clicks=0,
                        style={"backgroundColor": DANGER, "color": "#fff", "border": "none",
                               "padding": "6px 16px", "marginRight": "8px", "borderRadius": "4px", "cursor": "pointer"}),
            html.Span(id="replay-status-text",
                      children=f"{'Running' if is_running else 'Stopped'} — {status.get('progress_pct', 0):.1f}%",
                      style={"color": ACCENT if is_running else dim, "fontFamily": "monospace", "fontSize": "12px"}),
        ], style={"marginBottom": "10px"}),

        dcc.Store(id="store-replay-status", data=status),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 8: AGENT HUB — YAML-defined Trading Agents
# ═══════════════════════════════════════════════════════════════════════════════

def _build_agent_hub(archetypes: Optional[List[Dict]] = None, dark: bool = True) -> html.Div:
    """Build Agent Hub tab content."""
    bg = BG_CARD if dark else BG_CARD_LIGHT
    plot = BG_PLOT if dark else BG_PLOT_LIGHT
    text_color = TEXT if dark else TEXT_LIGHT
    dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

    if not archetypes:
        return html.Div("Loading agent archetypes...", style={"color": dim, "padding": "20px", "fontFamily": "monospace"})

    rows = []
    for a in archetypes:
        name = a.get("name", "unknown")
        desc = a.get("description", "")
        enabled = a.get("enabled", False)
        last_fired = a.get("last_fired", "Never")
        fire_count = a.get("fire_count", 0)
        status_color = ACCENT if enabled else dim

        rows.append(html.Div([
            html.Div([
                html.Span("●" if enabled else "○", style={"color": status_color, "marginRight": "8px"}),
                html.Strong(name, style={"color": text_color, "fontFamily": "monospace"}),
                html.Span(f" — {desc[:80]}", style={"color": dim, "fontSize": "11px"}),
            ]),
            html.Div([
                html.Span(f"Last fired: {last_fired}", style={"color": dim, "fontSize": "10px", "marginRight": "16px"}),
                html.Span(f"Fires: {fire_count}", style={"color": dim, "fontSize": "10px"}),
            ], style={"marginTop": "2px", "marginBottom": "8px"}),
        ], style={"borderBottom": f"1px solid {'#333' if dark else '#ddd'}", "padding": "6px 0"}))

    return html.Div([
        html.H4("Agent Archetypes", style={"color": text_color, "fontFamily": "monospace"}),
        html.Div(rows, style={"maxHeight": "500px", "overflowY": "auto"}),
    ], style={"padding": "10px", "backgroundColor": bg, "borderRadius": "4px"})


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 9: NEXUS — Social Trading Scaffold
# ═══════════════════════════════════════════════════════════════════════════════

def _build_nexus(dark: bool = True) -> html.Div:
    """Build Nexus social trading scaffold."""
    bg = BG_CARD if dark else BG_CARD_LIGHT
    text_color = TEXT if dark else TEXT_LIGHT
    dim = TEXT_DIM if dark else TEXT_DIM_LIGHT

    return html.Div([
        html.Div([
            html.H4("Nexus — Social Trading", style={"color": text_color, "fontFamily": "monospace"}),
            html.Span("PRIVATE BETA", style={"color": WARN, "fontSize": "10px", "marginLeft": "8px",
                                               "border": f"1px solid {WARN}", "padding": "2px 6px", "borderRadius": "3px"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),

        # Leaderboard
        html.H5("Leaderboard", style={"color": text_color}),
        html.Div("No entries yet. Be the first to share your track record.",
                 style={"color": dim, "fontSize": "12px", "padding": "8px 0"}),

        html.Hr(style={"borderColor": "#333" if dark else "#ddd"}),

        # Comments
        html.H5("Comment Thread", style={"color": text_color}),
        html.Div("Comments coming soon. Share trade ideas with the community.",
                 style={"color": dim, "fontSize": "12px", "padding": "8px 0"}),

        html.Hr(style={"borderColor": "#333" if dark else "#ddd"}),

        # Waitlist
        html.Div([
            html.P("Nexus is in private beta.", style={"color": dim, "fontSize": "12px"}),
            html.A("Join the waitlist", href="mailto:waitlist@confluencedecoder.ai",
                   style={"color": ACCENT, "fontSize": "12px"}),
        ]),
    ], style={"padding": "10px", "backgroundColor": bg, "borderRadius": "4px"})


# ═══════════════════════════════════════════════════════════════════════════════
# DASH APP CREATION + LAYOUT + CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

def create_dash_app(fastapi_app, url_base_pathname: str = "/dashboard/"):
    if not HAS_DASH:
        logger.warning("Dash not available — skipping UI mount")
        return None

    try:
        import dash
        from flask import Flask
        from starlette.middleware.wsgi import WSGIMiddleware

        flask_server = Flask(__name__)
        dash_app = dash.Dash(
            __name__, server=flask_server, url_base_pathname=url_base_pathname,
            external_stylesheets=[dbc.themes.DARKLY] if 'dbc' in dir() else [],
            suppress_callback_exceptions=True, update_title=None,
            meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
        )
        # Use WSGIMiddleware as an ASGI sub-application
        wsgi_app = WSGIMiddleware(dash_app.server)
        mount_path = url_base_pathname.rstrip('/')
        fastapi_app.add_route(f"{mount_path}/{{path:path}}", wsgi_app, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
        fastapi_app.add_route(mount_path, wsgi_app, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])

        # ── Layout ──────────────────────────────────────────────────────────
        dash_app.layout = html.Div([
            # Header
            html.Div([
                html.H1("Confluence Decoder Terminal", style={
                    "color": ACCENT, "fontFamily": "monospace", "display": "inline-block",
                    "marginRight": "20px", "fontSize": "22px",
                }),
                html.Span(id="live-indicator", children="LIVE", style={
                    "color": DANGER, "fontFamily": "monospace", "fontSize": "12px", "verticalAlign": "super",
                }),
                html.Button("Light", id="theme-toggle", n_clicks=0, style={
                    "marginLeft": "auto", "backgroundColor": "#333", "color": TEXT,
                    "border": "none", "padding": "4px 12px", "borderRadius": "4px", "cursor": "pointer",
                    "fontFamily": "monospace", "fontSize": "11px",
                }),
                html.Button("?", id="help-btn", n_clicks=0, style={
                    "marginLeft": "8px", "backgroundColor": "#333", "color": TEXT,
                    "border": "none", "padding": "4px 10px", "borderRadius": "4px", "cursor": "pointer",
                    "fontFamily": "monospace", "fontSize": "11px",
                }),
            ], style={
                "padding": "8px 20px", "borderBottom": "1px solid #333",
                "backgroundColor": BG_DARK, "display": "flex", "alignItems": "center",
            }),

            # Ticker selector
            html.Div([
                html.Label("Ticker: ", style={"color": TEXT_DIM, "fontFamily": "monospace"}),
                dcc.Dropdown(
                    id="ticker-selector",
                    options=[{"label": t, "value": t} for t in ["SPY", "QQQ", "SPX"]],
                    value="SPY", clearable=False,
                    style={"width": "120px", "display": "inline-block", "backgroundColor": BG_CARD, "color": TEXT},
                ),
                html.Span(id="last-update", style={
                    "color": TEXT_DIM, "fontFamily": "monospace", "fontSize": "11px", "marginLeft": "20px",
                }),
            ], style={"padding": "8px 20px", "backgroundColor": BG_DARK, "borderBottom": "1px solid #222"}),

            # Tabs
            dcc.Tabs(
                id="main-tabs", value="heatseeker",
                children=[
                    dcc.Tab(label="Heatseeker", value="heatseeker",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Flowseeker", value="flowseeker",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Toxicity", value="toxicity",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Vol Surface", value="vol-surface",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Trinity", value="trinity",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Atlas", value="atlas",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Replay", value="replay",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Agent Hub", value="agent-hub",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                    dcc.Tab(label="Nexus", value="nexus",
                            style={"backgroundColor": BG_CARD, "color": TEXT_DIM, "border": "none"},
                            selected_style={"backgroundColor": "#0f3460", "color": ACCENT, "border": "none"}),
                ],
                style={"backgroundColor": BG_DARK, "borderBottom": "1px solid #333", "height": "36px"},
            ),

            # Tab content
            html.Div(id="tab-content", style={"padding": "10px", "backgroundColor": BG_DARK}),

            # Auto-refresh interval (5s)
            dcc.Interval(id="interval-component", interval=5000, n_intervals=0),

            # Data stores
            dcc.Store(id="store-chain", data={}),
            dcc.Store(id="store-flow", data=[]),
            dcc.Store(id="store-toxicity", data={}),
            dcc.Store(id="store-vol", data={}),
            dcc.Store(id="store-trinity", data={}),
            dcc.Store(id="store-atlas", data={}),
            dcc.Store(id="store-replay-status", data={"running": False}),
            dcc.Store(id="store-agent-hub", data=[]),
            dcc.Store(id="store-theme", data={"dark": True}),

            # Help modal
            html.Div(id="help-modal", children=[
                html.Div([
                    html.H4("Keyboard Shortcuts", style={"color": ACCENT}),
                    html.Pre(children="""
1-5: Jump to tabs (1=Heatseeker, 2=Flowseeker, ...)
A: Atlas  R: Replay  H: Agent Hub  N: Nexus
T: Toggle theme  M: Mute alerts  ?: Show this help
                    """, style={"color": TEXT, "fontFamily": "monospace", "fontSize": "12px"}),
                    html.Button("Close", id="help-close-btn", n_clicks=0),
                ], style={"backgroundColor": BG_CARD, "padding": "20px", "borderRadius": "8px",
                          "border": f"1px solid {ACCENT}", "maxWidth": "400px", "margin": "100px auto"}),
            ], style={"display": "none", "position": "fixed", "top": 0, "left": 0, "right": 0, "bottom": 0,
                      "backgroundColor": "rgba(0,0,0,0.7)", "zIndex": 1000}),
        ], style={"backgroundColor": BG_DARK, "minHeight": "100vh", "fontFamily": "monospace"})

        # ── Callbacks ────────────────────────────────────────────────────────

        # Fetch chain data
        @dash_app.callback(
            Output("store-chain", "data"), Output("last-update", "children"),
            Input("interval-component", "n_intervals"), State("ticker-selector", "value"),
        )
        def fetch_chain(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/chain/{ticker}?expiries=4"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data, f"Updated: {data.get('ts', 'now')}"
            except Exception as e:
                return {}, f"Error: {e}"

        # Fetch flow data
        @dash_app.callback(
            Output("store-flow", "data"),
            Input("interval-component", "n_intervals"), State("ticker-selector", "value"),
        )
        def fetch_flow(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/flowseeker/live?ticker={ticker}&limit=100"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data if isinstance(data, list) else data.get("flows", [])
            except Exception:
                return []

        # Fetch toxicity
        @dash_app.callback(
            Output("store-toxicity", "data"),
            Input("interval-component", "n_intervals"), State("ticker-selector", "value"),
        )
        def fetch_toxicity(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/toxicity-dashboard/{ticker}"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
                    return json.loads(resp.read().decode())
            except Exception:
                return {}

        # Fetch vol surface
        @dash_app.callback(
            Output("store-vol", "data"),
            Input("interval-component", "n_intervals"), State("ticker-selector", "value"),
        )
        def fetch_vol(n_intervals, ticker):
            import urllib.request
            try:
                url = f"http://localhost:8000/api/vol-surface/{ticker}"
                with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
                    return json.loads(resp.read().decode())
            except Exception:
                return {}

        # Fetch trinity
        @dash_app.callback(
            Output("store-trinity", "data"),
            Input("interval-component", "n_intervals"),
        )
        def fetch_trinity(n_intervals):
            import urllib.request
            try:
                with urllib.request.urlopen(urllib.request.Request("http://localhost:8000/api/trinity/align"), timeout=5) as resp:
                    return json.loads(resp.read().decode())
            except Exception:
                return {}

        # Fetch atlas overlays
        @dash_app.callback(
            Output("store-atlas", "data"),
            Input("interval-component", "n_intervals"),
            State("store-chain", "data"), State("ticker-selector", "value"),
        )
        def fetch_atlas(n_intervals, chain_data, ticker):
            import urllib.request
            try:
                spot = chain_data.get("spot", 0) if isinstance(chain_data, dict) else 0
                contracts = chain_data.get("contracts", []) if isinstance(chain_data, dict) else []
                from services.atlas_overlays import build_all_overlays
                overlays = build_all_overlays(spot=spot, contracts=contracts)
                return {"spot": spot, "contracts": contracts, "overlays": overlays, "ohlc": chain_data.get("ohlc", [])}
            except Exception:
                return {}

        # Fetch agent hub
        @dash_app.callback(
            Output("store-agent-hub", "data"),
            Input("interval-component", "n_intervals"),
        )
        def fetch_agent_hub(n_intervals):
            import urllib.request
            try:
                with urllib.request.urlopen(urllib.request.Request("http://localhost:8000/api/agent-hub/archetypes"), timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                return data.get("archetypes", [])
            except Exception:
                return []

        # Theme toggle
        @dash_app.callback(
            Output("store-theme", "data"),
            Input("theme-toggle", "n_clicks"),
            State("store-theme", "data"),
        )
        def toggle_theme(n_clicks, current):
            if n_clicks == 0:
                return current or {"dark": True}
            return {"dark": not current.get("dark", True)}

        # Help modal
        @dash_app.callback(
            Output("help-modal", "style"),
            Input("help-btn", "n_clicks"), Input("help-close-btn", "n_clicks"),
            State("help-modal", "style"),
        )
        def toggle_help(n_open, n_close, current_style):
            ctx = dash.callback_context
            if not ctx.triggered:
                return {"display": "none"}
            btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
            if btn_id == "help-btn":
                return {"position": "fixed", "top": 0, "left": 0, "right": 0, "bottom": 0,
                        "backgroundColor": "rgba(0,0,0,0.7)", "zIndex": 1000}
            return {"display": "none"}

        # Render tab content
        @dash_app.callback(
            Output("tab-content", "children"),
            Input("main-tabs", "value"), Input("interval-component", "n_intervals"),
            State("store-chain", "data"), State("store-flow", "data"),
            State("store-toxicity", "data"), State("store-vol", "data"),
            State("store-trinity", "data"), State("store-atlas", "data"),
            State("store-agent-hub", "data"), State("store-theme", "data"),
            State("ticker-selector", "value"),
        )
        def render_tab(tab, n_intervals, chain_data, flow_data, tox_data, vol_data, trinity_data, atlas_data, agent_data, theme_data, ticker):
            dark = (theme_data or {}).get("dark", True)

            if tab == "heatseeker":
                spot = chain_data.get("spot", 0) if isinstance(chain_data, dict) else 0
                contracts = chain_data.get("contracts", []) if isinstance(chain_data, dict) else []

                # Read toggle state from store (with I-8 NaN guard)
                toggle_state = _sanitize_state_dict({})  # default; actual state read via callback

                # Extract expiry dates from chain data for the dropdown
                expiry_dates = []
                if isinstance(chain_data, dict):
                    seen = set()
                    for c in chain_data.get("contracts", []):
                        exp = c.get("expiry", c.get("expiration", ""))
                        if exp and exp not in seen:
                            seen.add(exp)
                            expiry_dates.append(exp)
                    expiry_dates.sort()

                sidebar = _build_heatseeker_toggles(expiry_dates=expiry_dates)
                fig = _build_gex_heatmap(spot=spot, contracts=contracts, dark=dark)
                graph = dcc.Graph(
                    id="heatseeker-graph",
                    figure=fig,
                    style={"height": "650px"},
                    config={"responsive": True},
                )
                return html.Div([
                    html.Div([
                        sidebar,
                        html.Div(graph, style={"flex": 1}),
                    ], style={"display": "flex", "flexDirection": "row"}),
                ])

            elif tab == "flowseeker":
                fig = _build_flow_ticker(flow_data, dark=dark)
                return dcc.Graph(figure=fig, style={"height": "650px"})

            elif tab == "toxicity":
                tox = tox_data if isinstance(tox_data, dict) else {}
                fig = _build_toxicity_dashboard(
                    vpin_cdf=tox.get("vpin_cdf", 0),
                    qi_zscore=tox.get("qi_zscore", 0),
                    fragility_score=tox.get("fragility_score", 0),
                    retail_flow_score=tox.get("retail_flow_score", 0),
                    regime=tox.get("regime", "NORMAL"),
                    history_vpin=tox.get("history_vpin"),
                    history_qi=tox.get("history_qi"),
                    history_ts=tox.get("history_ts"),
                    dark=dark,
                )
                return dcc.Graph(figure=fig, style={"height": "900px"})

            elif tab == "vol-surface":
                spot = chain_data.get("spot", 0) if isinstance(chain_data, dict) else 0
                contracts = chain_data.get("contracts", []) if isinstance(chain_data, dict) else []
                fig = _build_vol_surface(spot=spot, contracts=contracts, ticker=ticker,
                    grid_strikes=vol_data.get("grid_strikes") if isinstance(vol_data, dict) else None,
                    grid_expiries=vol_data.get("grid_expiries") if isinstance(vol_data, dict) else None,
                    iv_grid=vol_data.get("iv_grid") if isinstance(vol_data, dict) else None,
                    atm_skew=vol_data.get("atm_skew") if isinstance(vol_data, dict) else None,
                    butterfly=vol_data.get("butterfly") if isinstance(vol_data, dict) else None, dark=dark)
                return dcc.Graph(figure=fig, style={"height": "800px"})

            elif tab == "trinity":
                fig = _build_trinity_dashboard(
                    score=trinity_data.get("score", 0) if isinstance(trinity_data, dict) else 0,
                    regime=trinity_data.get("regime", "NONE") if isinstance(trinity_data, dict) else "NONE",
                    spy_zg=trinity_data.get("spy_zg") if isinstance(trinity_data, dict) else None,
                    qqq_zg=trinity_data.get("qqq_zg") if isinstance(trinity_data, dict) else None,
                    spx_zg=trinity_data.get("spx_zg") if isinstance(trinity_data, dict) else None,
                    cross_corr=trinity_data.get("cross_correlation") if isinstance(trinity_data, dict) else None,
                    aligned_levels=trinity_data.get("aligned_levels") if isinstance(trinity_data, dict) else None,
                    dark=dark)
                return dcc.Graph(figure=fig, style={"height": "850px"})

            elif tab == "atlas":
                ohlc = (atlas_data or {}).get("ohlc", [])
                overlays = (atlas_data or {}).get("overlays", {})
                fig = _build_atlas_chart(ohlc_data=ohlc, overlays=overlays, dark=dark)
                return html.Div([
                    dcc.Dropdown(id="atlas-time-window", options=[
                        {"label": "1 hour", "value": "1h"}, {"label": "4 hours", "value": "4h"},
                        {"label": "1 day", "value": "1d"}, {"label": "1 week", "value": "1w"},
                    ], value="4h", clearable=False, style={"width": "120px", "marginBottom": "8px"}),
                    dcc.Graph(figure=fig, style={"height": "700px"}),
                ])

            elif tab == "replay":
                replay_status = {}
                return html.Div([
                    _build_replay_controls(replay_status=replay_status, dark=dark),
                    dcc.Graph(figure=_empty_figure("Select a time range and press Play", dark), style={"height": "600px"}),
                ])

            elif tab == "agent-hub":
                return _build_agent_hub(archetypes=agent_data, dark=dark)

            elif tab == "nexus":
                return _build_nexus(dark=dark)

            return html.Div("Select a tab", style={"color": TEXT_DIM if dark else TEXT_DIM_LIGHT, "padding": "20px"})

        # ═══════════════════════════════════════════════════════════════════════
        # ROUND7: TOGGLE CALLBACKS
        # ═══════════════════════════════════════════════════════════════════════

        # I-8: Persist toggle state — save all toggle values to dcc.Store
        @dash_app.callback(
            Output("heatseeker-toggle-state", "data"),
            Input("heatseeker-view-toggle", "value"),
            Input("heatseeker-mode-toggle", "value"),
            Input("heatseeker-indicator-toggle", "value"),
            Input("heatseeker-dte-toggle", "value"),
            Input("heatseeker-expiries-toggle", "value"),
            prevent_initial_call=True,
        )
        def save_toggle_state(view, mode, indicators, dte_range, expiries):
            """Persist all toggle state to dcc.Store as JSON dict. I-8 NaN guard."""
            state = {
                "view": _safe_json_value(view) or "GEX",
                "mode": _safe_json_value(mode) or "absolute",
                "indicators": _safe_json_value(indicators) or [],
                "dte_min": _safe_json_value(dte_range[0]) if isinstance(dte_range, list) and len(dte_range) == 2 else 0,
                "dte_max": _safe_json_value(dte_range[1]) if isinstance(dte_range, list) and len(dte_range) == 2 else 365,
                "expiries": _safe_json_value(expiries) or [],
            }
            return _sanitize_state_dict(state)

        # Render Heatseeker graph from toggle state (partial figure update)
        @dash_app.callback(
            Output("heatseeker-graph", "figure"),
            Input("heatseeker-toggle-state", "data"),
            Input("interval-component", "n_intervals"),
            State("store-chain", "data"),
            State("store-theme", "data"),
            prevent_initial_call=True,
        )
        def render_heatseeker_graph(toggle_state, n_intervals, chain_data, theme_data):
            """Rebuild Heatseeker figure from toggle state. Partial update via Graph.figure."""
            dark = (theme_data or {}).get("dark", True)

            # I-8: sanitize stored state
            state = _sanitize_state_dict(toggle_state or {})

            view = state.get("view", "GEX")
            mode = state.get("mode", "absolute")
            indicators = state.get("indicators", [])
            dte_min = state.get("dte_min", 0)
            dte_max = state.get("dte_max", 365)
            selected_expiries = state.get("expiries", [])

            # Extract data from chain store
            spot = 0.0
            contracts = []
            king_nodes = []
            air_pockets = []
            zero_gamma = None

            if isinstance(chain_data, dict):
                spot = float(chain_data.get("spot", 0) or 0)
                contracts = chain_data.get("contracts", []) or []
                king_nodes = chain_data.get("king_nodes", []) or []
                air_pockets = chain_data.get("air_pockets", []) or []
                zg_val = chain_data.get("zero_gamma", None)
                zero_gamma = float(zg_val) if zg_val is not None else None

            # Filter contracts by DTE range
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            filtered_contracts = []
            for c in contracts:
                exp_str = c.get("expiry", c.get("expiration", ""))
                if exp_str:
                    try:
                        exp_dt = datetime.strptime(exp_str[:10], "%Y-%m-%d")
                        dte = (exp_dt - now).days
                        if dte_min <= dte <= dte_max:
                            filtered_contracts.append(c)
                    except (ValueError, TypeError):
                        filtered_contracts.append(c)
                else:
                    filtered_contracts.append(c)

            # Further filter by selected expiries (empty = all)
            if selected_expiries:
                filtered_contracts = [
                    c for c in filtered_contracts
                    if (c.get("expiry", c.get("expiration", "")) in selected_expiries)
                ]

            # Filter overlays by indicator toggle
            show_king_nodes = "king_nodes" in indicators
            show_air_pockets = "air_pockets" in indicators

            kn = king_nodes if show_king_nodes else None
            ap = air_pockets if show_air_pockets else None

            # Build the appropriate heatmap view
            try:
                if filtered_contracts:
                    from services.gex_aggregator import GexAggregator
                    agg = GexAggregator()
                    result = agg.compute(spot, filtered_contracts)
                    strikes = result.get("strikes", [])
                    expiries_list = result.get("expiries", [])
                    surface = result.get("gex_surface", [])
                else:
                    strikes = []
                    expiries_list = []
                    surface = None

                if not strikes or surface is None:
                    return _empty_figure(f"Waiting for {view} data...", dark)

                # Serialize for cache key
                surface_json = json.dumps(surface)
                strikes_json = json.dumps(strikes)
                expiries_json = json.dumps(expiries_list)
                kn_json = json.dumps(kn) if kn else ""
                ap_json = json.dumps(ap) if ap else ""
                indicators_json = json.dumps(indicators)
                zg = zero_gamma if zero_gamma is not None else 0.0

                fig = _cached_build_heatmap(
                    view=view,
                    mode=mode,
                    spot=round(spot, 2),
                    gex_surface_json=surface_json,
                    strikes_json=strikes_json,
                    expiries_json=expiries_json,
                    king_nodes_json=kn_json,
                    air_pockets_json=ap_json,
                    zero_gamma=zg,
                    indicators_json=indicators_json,
                )
                return fig

            except Exception as e:
                logger.error(f"Render heatseeker error: {e}")
                return _error_figure(str(e), dark)

        # Keyboard shortcuts via clientside callback
        clientside_callback(
            """
            function(n_clicks) {
                // Keyboard shortcuts handled via document.addEventListener
                return window.dash_clientside.no_update;
            }
            """,
            Output("main-tabs", "value"),
            Input("interval-component", "n_intervals"),
        )

        # Add keyboard shortcut JS
        dash_app.index_string = '''
        <!DOCTYPE html>
        <html>
            <head>
                {%metas%}
                <title>Confluence Decoder</title>
                {%favicon%}
                {%css%}
                <script>
                document.addEventListener('keydown', function(e) {
                    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
                    var tabs = {'1':'heatseeker','2':'flowseeker','3':'toxicity','4':'vol-surface','5':'trinity','6':'atlas','7':'replay','8':'agent-hub','9':'nexus'};
                    if (tabs[e.key]) {
                        document.getElementById('main-tabs').value = tabs[e.key];
                    }
                    if (e.key === '?' || e.key === '/') {
                        var modal = document.getElementById('help-modal');
                        if (modal) modal.style.display = modal.style.display === 'none' ? 'block' : 'none';
                    }
                    if (e.key === 't' || e.key === 'T') {
                        var btn = document.getElementById('theme-toggle');
                        if (btn) btn.click();
                    }
                    if (e.key === 'm' || e.key === 'M') {
                        // Mute alerts — toggle notification permission
                        if ('Notification' in window && Notification.permission === 'granted') {
                            // Already granted, show muted indicator
                        } else if ('Notification' in window) {
                            Notification.requestPermission();
                        }
                    }
                });
                // Request notification permission on first load
                if ('Notification' in window && Notification.permission === 'default') {
                    Notification.requestPermission();
                }
                </script>
                <style>
                @media (max-width: 768px) {
                    .dash-graph { height: 400px !important; }
                    div[data-dash-column] { width: 100% !important; }
                }
                </style>
            </head>
            <body>
                {%app_entry%}
                <footer>
                    {%config%}
                    {%scripts%}
                    {%renderer%}
                </footer>
            </body>
        </html>
        '''

        logger.info(f"Dash UI mounted at {url_base_pathname}")
        return dash_app

    except Exception as e:
        logger.error(f"Failed to create Dash app: {e}")
        return None
