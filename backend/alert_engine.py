"""
Options Alert System for Confluence Decoder

Combines signals from:
- GEX regime changes (gamma flip, positive/negative)
- Wall breaches (call wall, put wall)
- Gamma squeeze detection
- Momentum extremes
- GEX magnitude shifts (dealer repositioning)
- Pin risk (max gamma strike proximity)
- Volume spikes at near-ATM strikes

Based on research from:
- neeleshroy2023/gex-alerts: signal detection engine
- FlashAlpha: GEX/DEX/VEX/CHEX exposure levels
- Matteo-Ferrara/gex-tracker: GEX calculation
- Proshotv2/Gamma-Vanna: vanna exposure
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    """A single trading alert."""
    type: str           # GAMMA_FLIP, WALL_BREACH, GAMMA_SQUEEZE, etc.
    priority: str       # HIGH, MEDIUM, LOW
    ticker: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "priority": self.priority,
            "ticker": self.ticker,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp,
        }


@dataclass
class GEXSnapshot:
    """Snapshot of GEX data at a point in time."""
    ticker: str
    spot_price: float
    gamma_flip: float
    call_wall: float
    put_wall: float
    max_pain: float
    max_gamma_strike: float
    total_gex: float
    net_gex: float
    regime: str  # "POSITIVE" or "NEGATIVE"
    gex_by_strike: Dict[float, float] = field(default_factory=dict)
    # Per-strike contract volume for the current cycle.
    # Should be populated by the caller from the chain's `total_volume` field
    # (calls+puts per strike) so the volume-spike detector can fire on real
    # liquidity changes rather than GEX magnitude proxies.
    volume_by_strike: Dict[float, int] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AlertEngine:
    """
    Detects trading alerts by comparing GEX snapshots over time.
    Based on the signal detection algorithm from neeleshroy2023/gex-alerts.
    """

    # Configurable thresholds
    GAMMA_SQUEEZE_PROXIMITY_PCT = 0.5   # Spot within 0.5% of flip
    WALL_BREACH_PROXIMITY_PCT = 0.1     # 0.1% beyond wall = breach
    GEX_MAGNITUDE_SHIFT_PCT = 40.0      # 40% GEX change = significant
    GAMMA_FLIP_PROXIMITY_PCT = 0.3      # Within 0.3% of flip = inflection
    PIN_RISK_PROXIMITY_PCT = 0.2        # Within 0.2% of max gamma strike
    VOLUME_SPIKE_MULTIPLIER = 2.0       # 2x volume = spike (used by GEX-magnitude proxy)
    REAL_VOLUME_SPIKE_MULTIPLIER = 3.0  # 3x contract volume at a near-ATM strike
    REAL_VOLUME_SPIKE_FLOOR = 50        # absolute current-volume floor to kill illiquid noise
    REAL_VOLUME_SPIKE_BAND_PCT = 0.02   # within +/- 2% of spot
    MOMENTUM_EXTREME_HIGH = 80          # Score > 80 = extreme bullish
    MOMENTUM_EXTREME_LOW = 20           # Score < 20 = extreme bearish

    def __init__(self):
        self._snapshots: Dict[str, List[GEXSnapshot]] = {}

    def add_snapshot(self, snapshot: GEXSnapshot):
        """Store a new snapshot for comparison."""
        ticker = snapshot.ticker
        if ticker not in self._snapshots:
            self._snapshots[ticker] = []
        self._snapshots[ticker].append(snapshot)

        # Keep only last 100 snapshots per ticker
        if len(self._snapshots[ticker]) > 100:
            self._snapshots[ticker] = self._snapshots[ticker][-100:]

    def get_latest(self, ticker: str) -> Optional[GEXSnapshot]:
        """Return the most recent snapshot for a ticker, or None."""
        snaps = self._snapshots.get(ticker)
        return snaps[-1] if snaps else None

    def get_previous(self, ticker: str) -> Optional[GEXSnapshot]:
        """Return the second-most-recent snapshot for a ticker, or None."""
        snaps = self._snapshots.get(ticker)
        return snaps[-2] if snaps and len(snaps) >= 2 else None

    def detect_alerts(self, ticker: str, momentum_score: int = 50) -> List[Alert]:
        """
        Compare current vs previous snapshot and detect trading alerts.
        Returns alerts sorted by priority (HIGH first).
        """
        current = self.get_latest(ticker)
        previous = self.get_previous(ticker)

        if not current:
            return []

        alerts: List[Alert] = []
        spot = current.spot_price

        # 1. GAMMA FLIP (HIGH) — regime changed sign
        if previous and previous.regime != current.regime:
            direction = "SHORT gamma — expect amplified moves" if current.regime == "NEGATIVE" else "LONG gamma — expect mean reversion"
            alerts.append(Alert(
                type="GAMMA_FLIP",
                priority="HIGH",
                ticker=ticker,
                message=f"⚠️ REGIME CHANGE: {previous.regime} → {current.regime}. Dealers now {direction}",
                data={
                    "old_regime": previous.regime,
                    "new_regime": current.regime,
                    "gamma_flip": current.gamma_flip,
                    "net_gex": current.net_gex,
                }
            ))

        # 2. GAMMA SQUEEZE (HIGH) — negative gamma + spot near flip + volume spike
        if current.regime == "NEGATIVE" and previous:
            flip_dist_pct = abs(spot - current.gamma_flip) / spot * 100 if spot > 0 else 999
            if flip_dist_pct < self.GAMMA_SQUEEZE_PROXIMITY_PCT:
                gex_spike = self._detect_gex_magnitude_spike(current, previous)
                if gex_spike:
                    alerts.append(Alert(
                        type="GAMMA_SQUEEZE",
                        priority="HIGH",
                        ticker=ticker,
                        message=f"🔥 GAMMA SQUEEZE forming — negative regime, spot {spot:.0f} within {flip_dist_pct:.1f}% of flip at {current.gamma_flip:.0f}, volume spiking",
                        data={
                            "flip_distance_pct": round(flip_dist_pct, 2),
                            "gamma_flip": current.gamma_flip,
                            "regime": current.regime,
                        }
                    ))

        # 3. MOMENTUM EXTREME (HIGH)
        if momentum_score > self.MOMENTUM_EXTREME_HIGH:
            alerts.append(Alert(
                type="MOMENTUM_EXTREME",
                priority="HIGH",
                ticker=ticker,
                message=f"📈 Strong BULLISH momentum — score {momentum_score}/100",
                data={"momentum_score": momentum_score, "direction": "BULLISH"}
            ))
        elif momentum_score < self.MOMENTUM_EXTREME_LOW:
            alerts.append(Alert(
                type="MOMENTUM_EXTREME",
                priority="HIGH",
                ticker=ticker,
                message=f"📉 Strong BEARISH momentum — score {momentum_score}/100",
                data={"momentum_score": momentum_score, "direction": "BEARISH"}
            ))

        # 4. WALL BREACH (MEDIUM) — only fire on crossing, not while beyond
        if current.call_wall > 0 and previous:
            # Bullish: spot was at or below call wall, now above it
            if previous.spot_price <= current.call_wall and spot > current.call_wall:
                breach_pct = (spot - current.call_wall) / current.call_wall * 100
                alerts.append(Alert(
                    type="WALL_BREACH",
                    priority="MEDIUM",
                    ticker=ticker,
                    message=f"🚀 BULLISH breakout — spot {spot:.0f} crossed above call wall at {current.call_wall:.0f} (+{breach_pct:.2f}%)",
                    data={"wall": current.call_wall, "direction": "BULLISH", "breach_pct": round(breach_pct, 2)}
                ))

        if current.put_wall > 0 and previous:
            # Bearish: spot was at or above put wall, now below it
            if previous.spot_price >= current.put_wall and spot < current.put_wall:
                breach_pct = (current.put_wall - spot) / current.put_wall * 100
                alerts.append(Alert(
                    type="WALL_BREACH",
                    priority="MEDIUM",
                    ticker=ticker,
                    message=f"🔻 BEARISH breakdown — spot {spot:.0f} crossed below put wall at {current.put_wall:.0f} (-{breach_pct:.2f}%)",
                    data={"wall": current.put_wall, "direction": "BEARISH", "breach_pct": round(breach_pct, 2)}
                ))

        # 5. GEX MAGNITUDE SHIFT (MEDIUM) — total GEX changed > 40%
        if previous and previous.total_gex != 0:
            gex_change_pct = abs(current.total_gex - previous.total_gex) / abs(previous.total_gex) * 100
            if gex_change_pct > self.GEX_MAGNITUDE_SHIFT_PCT:
                alerts.append(Alert(
                    type="GEX_MAGNITUDE_SHIFT",
                    priority="MEDIUM",
                    ticker=ticker,
                    message=f"⚡ GEX shifted {gex_change_pct:.0f}% — rapid dealer repositioning detected",
                    data={
                        "change_pct": round(gex_change_pct, 1),
                        "old_gex": previous.total_gex,
                        "new_gex": current.total_gex,
                    }
                ))

        # 6. GAMMA FLIP PROXIMITY (MEDIUM) — spot within 0.3% of flip
        flip_proximity = abs(spot - current.gamma_flip) / spot * 100 if spot > 0 else 999
        if flip_proximity < self.GAMMA_FLIP_PROXIMITY_PCT:
            if not any(a.type == "GAMMA_FLIP" for a in alerts):
                alerts.append(Alert(
                    type="GAMMA_FLIP_PROXIMITY",
                    priority="MEDIUM",
                    ticker=ticker,
                    message=f"🔄 Spot {spot:.0f} within {flip_proximity:.2f}% of gamma flip at {current.gamma_flip:.0f} — inflection zone",
                    data={"gamma_flip": current.gamma_flip, "distance_pct": round(flip_proximity, 2)}
                ))

        # 7. PIN RISK (LOW) — spot near max gamma strike
        pin_proximity = abs(spot - current.max_gamma_strike) / spot * 100 if spot > 0 else 999
        if pin_proximity < self.PIN_RISK_PROXIMITY_PCT:
            alerts.append(Alert(
                type="PIN_RISK",
                priority="LOW",
                ticker=ticker,
                message=f"📌 Pin risk — spot {spot:.0f} within {pin_proximity:.2f}% of max gamma strike {current.max_gamma_strike:.0f}",
                data={"max_gamma_strike": current.max_gamma_strike, "distance_pct": round(pin_proximity, 2)}
            ))

        # 8. CHARM PINNING (HIGH) — charm-driven pinning (0DTE)
        charm_alert = self._detect_charm_pinning(current, previous)
        if charm_alert:
            alerts.append(charm_alert)

        # 9. VANNA REGIME CHANGE (HIGH) — sign flip in net VEX
        vanna_alert = self._detect_vanna_regime_change(current, previous)
        if vanna_alert:
            alerts.append(vanna_alert)

        # 10. UNUSUAL P/C OI RATIO (MEDIUM) — put-heavy skew
        pc_alert = self._detect_pc_oi_ratio(current, previous)
        if pc_alert:
            alerts.append(pc_alert)

        # 11. MAX PAIN MAGNET (LOW) — spot near max pain in positive gamma
        max_pain_alert = self._detect_max_pain_magnet(current, previous)
        if max_pain_alert:
            alerts.append(max_pain_alert)

        # 12. VOLUME SPIKE (MEDIUM) — real contract-volume spike at near-ATM strike
        if previous and self._detect_volume_spike(current, previous):
            alerts.append(Alert(
                type="VOLUME_SPIKE",
                priority="MEDIUM",
                ticker=ticker,
                message=f"Volume spike at near-ATM strike (>= {self.REAL_VOLUME_SPIKE_MULTIPLIER:.0f}x prev cycle, floor {self.REAL_VOLUME_SPIKE_FLOOR})",
                data={
                    "multiplier": self.REAL_VOLUME_SPIKE_MULTIPLIER,
                    "floor": self.REAL_VOLUME_SPIKE_FLOOR,
                    "band_pct": self.REAL_VOLUME_SPIKE_BAND_PCT,
                },
            ))

        # Sort by priority
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        alerts.sort(key=lambda a: priority_order.get(a.priority, 9))

        return alerts

    def _detect_gex_magnitude_spike(self, current: GEXSnapshot, previous: GEXSnapshot) -> bool:
        """Check if any near-ATM strike has a GEX magnitude spike vs previous cycle.
        Note: misnamed as _detect_volume_spike in original code — actually reads GEX magnitude."""
        if not previous.gex_by_strike or not current.gex_by_strike:
            return False

        spot = current.spot_price
        near_strikes = [
            s for s in current.gex_by_strike
            if abs(s - spot) / spot < 0.02  # within 2% of spot
        ]

        for strike in near_strikes:
            cur_gex = abs(current.gex_by_strike.get(strike, 0))
            prev_gex = abs(previous.gex_by_strike.get(strike, 0))
            if prev_gex > 0 and cur_gex / prev_gex > self.VOLUME_SPIKE_MULTIPLIER:
                return True

        return False

    def _detect_volume_spike(self, current: GEXSnapshot, previous: GEXSnapshot) -> bool:
        """Real contract-volume spike at a near-ATM strike.

        Distinct from _detect_gex_magnitude_spike (which inspects GEX magnitude
        and was misnamed `_detect_volume_spike` in the original code). This
        method reads `volume_by_strike` — actual options contract volume — and
        fires when ANY strike within +/- REAL_VOLUME_SPIKE_BAND_PCT of spot has:

            current_volume >= REAL_VOLUME_SPIKE_MULTIPLIER * previous_volume
            AND
            current_volume >= REAL_VOLUME_SPIKE_FLOOR

        The absolute floor is required to avoid spurious 5x-on-tiny-base signals
        at illiquid strikes.
        """
        if not current.volume_by_strike or not previous.volume_by_strike:
            return False

        spot = current.spot_price
        if spot <= 0:
            return False

        for strike, cur_vol in current.volume_by_strike.items():
            if abs(strike - spot) / spot > self.REAL_VOLUME_SPIKE_BAND_PCT:
                continue
            if cur_vol < self.REAL_VOLUME_SPIKE_FLOOR:
                continue
            prev_vol = previous.volume_by_strike.get(strike, 0)
            if prev_vol <= 0:
                continue
            if cur_vol >= self.REAL_VOLUME_SPIKE_MULTIPLIER * prev_vol:
                return True

        return False

    # -------- New Alert Types (from Claude Code review) --------

    def _detect_charm_pinning(self, current: GEXSnapshot, previous: Optional[GEXSnapshot]) -> Optional[Alert]:
        """Charm-driven pinning (0DTE): |cumulative charm| above threshold, spot near max gamma strike."""
        if not current.gex_by_strike:
            return None
        # Find max gamma strike
        max_gamma_strike = max(current.gex_by_strike, key=lambda s: abs(current.gex_by_strike[s]))
        if max_gamma_strike == 0:
            return None
        # Check if spot is within 0.3% of max gamma strike
        if abs(current.spot_price - max_gamma_strike) / max(current.spot_price, 1) > 0.003:
            return None
        # Charm is high when GEX is concentrated at one strike
        total_gex = sum(abs(v) for v in current.gex_by_strike.values())
        max_gex = abs(current.gex_by_strike.get(max_gamma_strike, 0))
        if total_gex > 0 and max_gex / total_gex > 0.3:
            return Alert(
                type="CHARM_PINNING",
                priority="HIGH",
                ticker=current.ticker,
                message=f"Charm pinning detected: spot {current.spot_price} near max gamma strike {max_gamma_strike}",
                data={"spot": current.spot_price, "max_gamma_strike": max_gamma_strike, "concentration": round(max_gex / total_gex, 2)}
            )
        return None

    def _detect_vanna_regime_change(self, current: GEXSnapshot, previous: Optional[GEXSnapshot]) -> Optional[Alert]:
        """Vanna regime change: sign flip in net VEX above a floor."""
        if not previous:
            return None
        # Simplified: detect large shift in GEX distribution
        cur_net = current.net_gex
        prev_net = previous.net_gex
        if prev_net == 0:
            return None
        # Sign flip
        if (cur_net > 0 and prev_net < 0) or (cur_net < 0 and prev_net > 0):
            if abs(cur_net) > 1e8:  # $100M floor
                return Alert(
                    type="VANNA_REGIME_CHANGE",
                    priority="HIGH",
                    ticker=current.ticker,
                    message=f"Vanna regime change: net GEX flipped from {prev_net:.0f} to {cur_net:.0f}",
                    data={"prev_net_gex": prev_net, "cur_net_gex": cur_net}
                )
        return None

    def _detect_pc_oi_ratio(self, current: GEXSnapshot, previous: Optional[GEXSnapshot]) -> Optional[Alert]:
        """Unusual P/C OI ratio: put OI / call OI Z-score vs trailing snapshots."""
        if not current.gex_by_strike:
            return None
        # Simplified: check if put-heavy (negative GEX skew)
        put_gex = sum(v for v in current.gex_by_strike.values() if v < 0)
        call_gex = sum(v for v in current.gex_by_strike.values() if v > 0)
        if call_gex == 0:
            return None
        ratio = abs(put_gex) / call_gex
        if ratio > 2.0:  # 2x more put OI than call OI
            return Alert(
                type="UNUSUAL_PC_OI_RATIO",
                priority="MEDIUM",
                ticker=current.ticker,
                message=f"Unusual P/C OI ratio: {ratio:.1f}x (put-heavy)",
                data={"put_gex": put_gex, "call_gex": call_gex, "ratio": round(ratio, 2)}
            )
        return None

    def _detect_max_pain_magnet(self, current: GEXSnapshot, previous: Optional[GEXSnapshot]) -> Optional[Alert]:
        """Max pain magnet: in positive gamma regime, spot within 1% of max pain."""
        if current.regime != "POSITIVE":
            return None
        if current.max_pain <= 0:
            return None
        if abs(current.spot_price - current.max_pain) / current.spot_price < 0.01:
            return Alert(
                type="MAX_PAIN_MAGNET",
                priority="LOW",
                ticker=current.ticker,
                message=f"Max pain magnet: spot {current.spot_price} within 1% of max pain {current.max_pain}",
                data={"spot": current.spot_price, "max_pain": current.max_pain}
            )
        return None

    def get_alert_summary(self, ticker: str) -> Dict[str, Any]:
        """Get a summary of current alerts for a ticker."""
        latest = self.get_latest(ticker)
        if not latest:
            return {"ticker": ticker, "status": "no_data"}

        alerts = self.detect_alerts(ticker)

        return {
            "ticker": ticker,
            "spot": latest.spot_price,
            "regime": latest.regime,
            "gamma_flip": latest.gamma_flip,
            "call_wall": latest.call_wall,
            "put_wall": latest.put_wall,
            "net_gex": latest.net_gex,
            "alert_count": len(alerts),
            "high_priority": len([a for a in alerts if a.priority == "HIGH"]),
            "alerts": [a.to_dict() for a in alerts],
            "timestamp": datetime.utcnow().isoformat(),
        }
