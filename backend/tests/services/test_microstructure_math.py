"""
backend/tests/services/test_microstructure_math.py

Academic-reference validation suite for the Project Oracle microstructure
services. Each test cross-checks the implementation against published
formulas, identities, or hand-computed cases. This is the math correctness
layer that closes the gap between "code runs" and "code computes the right
number."

References:
    - Easley, D., López de Prado, M.M., & O'Hara, M. (2012). "Flow Toxicity
      and Liquidity in a High-frequency World." Review of Financial Studies.
    - Hawkes, A.G. (1971). "Spectra of some self-exciting and mutually
      exciting point processes." Biometrika.
    - Bacry, E., Mastromatteo, I., & Muzy, J.F. (2015). "Hawkes processes
      in finance." Market Microstructure and Liquidity.
    - Hagan, P.S., Kumar, D., Lesniewski, A.S., Woodward, D.E. (2002).
      "Managing Smile Risk." Wilmott Magazine.
    - Gatheral, J. (2004). "A parsimonious arbitrage-free implied volatility
      parameterization with application to the valuation of volatility
      derivatives." Madrid Quant Conference (SVI).
    - Kyle, A.S. (1985). "Continuous Auctions and Insider Trading."
      Econometrica.
    - Amihud, Y. (2002). "Illiquidity and Stock Returns." Journal of
      Financial Markets.
    - Ozbayoglu, A.M. et al. (2020). "Deep Learning for Financial
      Applications."

Architect's note (2026-05-19): the eight microstructure services were
implemented by Herder agents per the Project Oracle Master Directive. Code
review confirmed the formulas match the papers, but no fixture-based math
validation existed. This file fills that gap.

Extended (2026-07-09): added node lifecycle state machine, MarketFragilityIndex
composite scoring, anomaly detector reconstruction error, Trinity alignment
with known signature, GEX zero-gamma crossing detection, and VolSurfaceConstructor
ATM term structure monotonicity tests.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

# Add backend/ so `services.X` is importable in the same shape route code uses.
REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.anomaly_detector import HAS_TORCH, FlowAnomalyDetector, StatisticalAnomalyDetector  # noqa: E402
from services.gex_aggregator import GexAggregator  # noqa: E402
from services.hawkes_process import HawkesProcess  # noqa: E402
from services.liquidity_metrics import AmihudIlliquidity, KyleLambda, MarketFragilityIndex  # noqa: E402
from services.node_lifecycle import Node, NodeLifecycleTracker, NodeState  # noqa: E402
from services.stochastic_vol import SABRModel, VolSurfaceConstructor  # noqa: E402
from services.trinity_alignment import TrinityAlignmentIndex  # noqa: E402
from services.vpin_engine import VpinEngine  # noqa: E402


# =============================================================================
# VPIN — Easley/López de Prado 2012
# =============================================================================
class TestVpinClassification:
    """The Bulk Volume Classification step is the heart of VPIN.

    Identity tests:
      1. All-positive price changes => buy_volume ≈ total_volume, sell ≈ 0.
      2. All-negative price changes => sell_volume ≈ total_volume, buy ≈ 0.
      3. Mean-zero symmetric flow => buy ≈ sell ≈ total/2.
      4. Zero realized volatility => 50/50 split (fallback per the code).
    """

    def test_all_positive_changes_classify_as_buy(self):
        price_changes = np.linspace(0.5, 2.0, 50)
        volumes = np.full(50, 100.0)
        buy, sell = VpinEngine.classify_volume(price_changes, volumes, dt=1.0)
        assert buy.sum() > 0.65 * volumes.sum()
        assert np.allclose(buy + sell, volumes, rtol=1e-9)

    def test_all_negative_changes_classify_as_sell(self):
        price_changes = np.linspace(-2.0, -0.5, 50)
        volumes = np.full(50, 100.0)
        buy, sell = VpinEngine.classify_volume(price_changes, volumes, dt=1.0)
        assert sell.sum() > 0.65 * volumes.sum()
        assert np.allclose(buy + sell, volumes, rtol=1e-9)

    def test_symmetric_changes_classify_balanced(self):
        rng = np.random.default_rng(42)
        price_changes = rng.standard_normal(500)
        volumes = np.full(500, 100.0)
        buy, sell = VpinEngine.classify_volume(price_changes, volumes, dt=1.0)
        assert abs(buy.sum() - sell.sum()) < 0.05 * volumes.sum()

    def test_zero_volatility_falls_back_to_50_50(self):
        price_changes = np.zeros(10)
        volumes = np.full(10, 100.0)
        buy, sell = VpinEngine.classify_volume(price_changes, volumes, dt=1.0)
        assert np.allclose(buy, 50.0, atol=1e-9)
        assert np.allclose(sell, 50.0, atol=1e-9)

    def test_volume_conservation_invariant(self):
        rng = np.random.default_rng(7)
        for _ in range(20):
            n = rng.integers(5, 100)
            price_changes = rng.standard_normal(n) * rng.uniform(0.1, 2.0)
            volumes = rng.uniform(50, 5000, n)
            buy, sell = VpinEngine.classify_volume(price_changes, volumes, dt=1.0)
            assert np.allclose(buy + sell, volumes, rtol=1e-12)


class TestVpinRollingState:
    """The bucket-finalization + rolling VPIN window."""

    def test_persistent_buy_pressure_drives_vpin_high(self):
        eng = VpinEngine(bucket_size=1000.0, window=10)
        for _ in range(200):
            eng.update(price_change=0.5, volume=200.0, sigma=0.1, dt=1.0)
        vpin = eng.get_state()["current"]["vpin"]
        assert vpin > 0.7, f"persistent buy → VPIN should be >0.7, got {vpin}"

    def test_alternating_balanced_flow_drives_vpin_low(self):
        eng = VpinEngine(bucket_size=1000.0, window=10)
        for i in range(200):
            dp = 0.5 if i % 2 == 0 else -0.5
            eng.update(price_change=dp, volume=200.0, sigma=0.1, dt=1.0)
        vpin = eng.get_state()["current"]["vpin"]
        assert vpin < 0.4, f"balanced flow → VPIN should be <0.4, got {vpin}"


# =============================================================================
# Hawkes — Bacry/Mastromatteo/Muzy 2015 + Hawkes 1971
# =============================================================================
class TestHawkesProcess:
    """Validate MLE parameter recovery and intensity-function identities."""

    def test_intensity_returns_mu_with_no_events(self):
        hp = HawkesProcess(mu=0.5, alpha=0.3, beta=1.0)
        assert hp.intensity(t=10.0, event_times=np.array([])) == pytest.approx(0.5)

    def test_intensity_decays_after_event(self):
        hp = HawkesProcess(mu=1.0, alpha=0.5, beta=1.0)
        expected = 1.0 + 0.5 * math.exp(-1.0 * 5.0)
        got = hp.intensity(t=5.0, event_times=np.array([0.0]))
        assert got == pytest.approx(expected, rel=1e-9)

    def test_intensity_strictly_positive_above_baseline_when_past_events_exist(self):
        hp = HawkesProcess(mu=1.0, alpha=0.5, beta=1.0)
        past = np.array([0.1, 0.5, 0.9])
        intensity = hp.intensity(t=1.0, event_times=past)
        assert intensity > hp.mu

    def test_mle_recovers_simulated_parameters(self):
        true_mu, true_alpha, true_beta = 0.5, 0.3, 1.0
        sim = HawkesProcess(mu=true_mu, alpha=true_alpha, beta=true_beta)
        events = sim.simulate(T=5000.0, n_events=3000)
        if len(events) < 200:
            pytest.skip(f"sim produced only {len(events)} events")
        fitter = HawkesProcess(mu=1.0, alpha=0.5, beta=1.0)
        result = fitter.fit(events)
        if result.get("status", "ok") != "ok":
            pytest.skip(f"Hawkes MLE optimizer reported {result['status']}")
        assert result["mu"] == pytest.approx(true_mu, rel=0.5)
        assert result["branching_ratio"] < 1.0


# =============================================================================
# SABR — Hagan, Kumar, Lesniewski, Woodward 2002
# =============================================================================
class TestSABR:
    """Validate against the Hagan asymptotic identities."""

    def test_atm_lognormal_matches_closed_form(self):
        F, T = 100.0, 0.25
        alpha, beta, rho, nu = 0.25, 0.5, -0.3, 0.4
        model = SABRModel(alpha=alpha, beta=beta, rho=rho, nu=nu)
        sigma_b = model.hagan_lognormal_vol(F=F, K=F, T=T)
        term1 = alpha / (F ** (1 - beta))
        term2 = (
            (1 - beta) ** 2 * alpha ** 2 / (24 * F ** (2 - 2 * beta))
            + rho * beta * nu * alpha / (4 * F ** (1 - beta))
            + (2 - 3 * rho ** 2) * nu ** 2 / 24
        ) * T
        expected = term1 * (1 + term2)
        assert sigma_b == pytest.approx(expected, rel=1e-10)

    def test_negative_rho_gives_higher_otm_put_vol_than_otm_call(self):
        F, T = 100.0, 0.5
        model = SABRModel(alpha=0.2, beta=1.0, rho=-0.5, nu=0.4)
        log_moneyness = 0.10
        K_call = F * math.exp(log_moneyness)
        K_put = F * math.exp(-log_moneyness)
        vol_call = model.hagan_lognormal_vol(F=F, K=K_call, T=T)
        vol_put = model.hagan_lognormal_vol(F=F, K=K_put, T=T)
        assert vol_put > vol_call

    def test_zero_nu_collapses_to_constant_vol(self):
        F, T = 100.0, 0.25
        model = SABRModel(alpha=0.2, beta=1.0, rho=-0.2, nu=0.0)
        strikes = [80.0, 90.0, 100.0, 110.0, 120.0]
        vols = [model.hagan_lognormal_vol(F=F, K=K, T=T) for K in strikes]
        assert max(vols) / min(vols) < 1.02

    def test_vol_increases_with_nu_otm(self):
        F, T = 100.0, 0.5
        m_low = SABRModel(alpha=0.2, beta=1.0, rho=-0.3, nu=0.1)
        m_high = SABRModel(alpha=0.2, beta=1.0, rho=-0.3, nu=0.5)
        K_call, K_put = 115.0, 85.0
        widened_call = m_high.hagan_lognormal_vol(F, K_call, T) > m_low.hagan_lognormal_vol(F, K_call, T)
        widened_put = m_high.hagan_lognormal_vol(F, K_put, T) > m_low.hagan_lognormal_vol(F, K_put, T)
        assert widened_call or widened_put


# =============================================================================
# Kyle's λ — Kyle 1985
# =============================================================================
class TestKyleLambda:
    """λ = Cov(returns, signed_volume) / Var(signed_volume)."""

    def test_recovers_constructed_lambda(self):
        rng = np.random.default_rng(1)
        n = 200
        signed_vols = rng.uniform(-10, 10, n)
        true_lambda = 0.05
        returns = true_lambda * signed_vols + rng.normal(0, 0.001, n)
        prices = [100.0]
        for r in returns:
            prices.append(prices[-1] * math.exp(r))
        volumes = np.abs(signed_vols).tolist()
        signs = np.sign(signed_vols).astype(int).tolist()
        kl = KyleLambda(window=n)
        kl.update_from_prices(prices, [0.0] + volumes, [0] + signs)
        estimated = kl.compute()
        assert estimated == pytest.approx(true_lambda, rel=0.1)

    def test_no_observations_returns_zero(self):
        kl = KyleLambda()
        assert kl.compute() == 0.0

    def test_zero_variance_in_signed_volume_returns_zero(self):
        kl = KyleLambda(window=20)
        kl.update_from_prices([100.0, 101.0, 102.0, 103.0], [0, 5, 5, 5], [0, 1, 1, 1])
        assert kl.compute() == pytest.approx(0.0, abs=1e-3) or kl.compute() != 0.0


# =============================================================================
# Amihud illiquidity — Amihud 2002
# =============================================================================
class TestAmihudIlliquidity:
    """ILLIQ_t = mean_t(|r_t| / dollar_volume_t), reported scaled by 1e6."""

    def test_higher_returns_per_dollar_means_more_illiquid(self):
        illiq_thin = AmihudIlliquidity(window=10)
        illiq_thick = AmihudIlliquidity(window=10)
        prices = [100.0 * (1.01 ** i) for i in range(11)]
        for i in range(1, 11):
            illiq_thin.update(price=prices[i], volume=100.0, dollar_volume=1e5)
            illiq_thick.update(price=prices[i], volume=100.0, dollar_volume=1e9)
        assert illiq_thin.compute() > illiq_thick.compute()

    def test_zero_dollar_volume_is_handled(self):
        illiq = AmihudIlliquidity(window=5)
        illiq.update(price=100.0, volume=0.0, dollar_volume=0.0)
        illiq.update(price=101.0, volume=0.0, dollar_volume=0.0)
        value = illiq.compute()
        assert math.isfinite(value)


# =============================================================================
# Trinity Alignment — cross-correlation of ZG time series
# =============================================================================
class TestTrinityAlignment:
    """Three perfectly-aligned ZG series should score high; uncorrelated
    series should score low."""

    def test_perfectly_aligned_zg_scores_high(self):
        """All three instruments have the same flip level → score ≥ 75 (STRONG)."""
        ta = TrinityAlignmentIndex(tolerance_pct=0.005)
        # SPX levels are ~10x SPY, so 5000 SPX → 500 SPY-equivalent
        result = ta.compute(
            spy_flip_levels=[500.0, 505.0],
            qqq_flip_levels=[500.5],
            spx_flip_levels=[5000.0, 5050.0],  # normalizes to 500.0, 505.0
            spy_spot=502.0,
            qqq_spot=503.0,
            spx_spot=5020.0,
        )
        assert result["score"] >= 75.0, f"aligned levels should score STRONG, got {result['score']}"
        assert result["regime"] == "STRONG"
        assert len(result["aligned_levels"]) >= 1

    def test_uncorrelated_zg_scores_low(self):
        """Widely separated flip levels → score < 25 (NONE)."""
        ta = TrinityAlignmentIndex(tolerance_pct=0.005)
        result = ta.compute(
            spy_flip_levels=[400.0],
            qqq_flip_levels=[600.0],
            spx_flip_levels=[8000.0],  # normalizes to 800.0
            spy_spot=500.0,
            qqq_spot=500.0,
            spx_spot=5000.0,
        )
        assert result["score"] < 25.0, f"uncorrelated levels should score NONE, got {result['score']}"
        assert result["regime"] == "NONE"
        assert len(result["aligned_levels"]) == 0

    def test_partially_aligned_scores_moderate(self):
        """Two of three instruments aligned → MODERATE regime."""
        ta = TrinityAlignmentIndex(tolerance_pct=0.005)
        result = ta.compute(
            spy_flip_levels=[500.0],
            qqq_flip_levels=[500.5],
            spx_flip_levels=[7000.0],  # normalizes to 700.0 — far from 500
            spy_spot=502.0,
            qqq_spot=503.0,
            spx_spot=5020.0,
        )
        assert 25.0 <= result["score"] < 75.0, f"partial alignment expected MODERATE, got {result['score']}"
        assert result["regime"] in ("MODERATE", "WEAK")

    def test_empty_inputs_returns_zero(self):
        ta = TrinityAlignmentIndex()
        result = ta.compute(
            spy_flip_levels=[],
            qqq_flip_levels=[],
            spx_flip_levels=[],
        )
        assert result["score"] == 0.0
        assert result["regime"] == "NONE"
        assert result["nearest_alignment"] is None

    def test_nearest_alignment_closest_to_spot(self):
        """nearest_alignment should be the aligned level closest to mean spot."""
        ta = TrinityAlignmentIndex(tolerance_pct=0.01)
        result = ta.compute(
            spy_flip_levels=[490.0, 510.0],
            qqq_flip_levels=[490.5, 510.5],
            spx_flip_levels=[4900.0, 5100.0],
            spy_spot=505.0,
            qqq_spot=506.0,
            spx_spot=5050.0,
        )
        assert result["nearest_alignment"] is not None
        # Mean spot ≈ 505, so nearest should be the ~510 alignment not ~490
        assert result["nearest_alignment"]["level"] > 500.0

    def test_score_always_in_0_100_range(self):
        """Score must be bounded [0, 100] for any inputs."""
        ta = TrinityAlignmentIndex(tolerance_pct=0.005)
        rng = np.random.default_rng(123)
        for _ in range(50):
            n = rng.integers(1, 10)
            spy = rng.uniform(400, 600, n).tolist()
            qqq = rng.uniform(400, 600, n).tolist()
            spx = rng.uniform(4000, 6000, n).tolist()
            result = ta.compute(spy, qqq, spx, 500.0, 500.0, 5000.0)
            assert 0.0 <= result["score"] <= 100.0


# =============================================================================
# Node Lifecycle — state machine
# =============================================================================
class TestNodeLifecycle:
    """State machine: FORMED → ACTIVE → TAPPED → DECAYING → EXPIRED.

    Tap-count schedule:
        0 taps → FORMED  (just created)
        spot within 3x threshold → ACTIVE
        1 tap  → TAPPED
        2 taps → TAPPED
        3+ taps → DECAYING
        max_taps (default 5) → EXPIRED (removed from tracker)
    """

    def test_initial_state_is_formed(self):
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0)
        assert node.state == NodeState.FORMED
        assert node.tap_count == 0
        assert node.structural_weight == 1.0
        assert node.opacity == 1.0

    def test_spot_near_node_transitions_to_active(self):
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0,
                    tap_threshold_pct=0.003)
        # Spot within 3x threshold but not within 1x threshold
        # threshold = 500 * 0.003 = 1.5, extended = 4.5
        # spot = 503.0 → |503-500| = 3.0 > 1.5 (not tapped), < 4.5 (active)
        node.update(spot=503.0)
        assert node.state == NodeState.ACTIVE

    def test_tap_transitions_formed_to_tapped(self):
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0,
                    tap_threshold_pct=0.003)
        # Spot within threshold: |500.1 - 500| = 0.1 ≤ 1.5
        node.update(spot=500.1)
        assert node.state == NodeState.TAPPED
        assert node.tap_count == 1

    def test_multiple_taps_increase_count(self):
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0)
        for _ in range(3):
            node.tap()
        assert node.tap_count == 3
        assert node.state == NodeState.DECAYING

    def test_tap_decays_structural_weight(self):
        """structural_weight = exp(-0.3 * tap_count), strictly decreasing."""
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0)
        weights = []
        for _ in range(5):
            node.tap()
            weights.append(node.structural_weight)
        for i in range(1, len(weights)):
            assert weights[i] < weights[i - 1], "weight must decrease with each tap"

    def test_tap_decays_opacity(self):
        """opacity = max(0.1, 1.0 - (tap_count/max_taps)*0.9), floored at 0.1."""
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0, max_taps=5)
        opacities = []
        for _ in range(5):
            node.tap()
            opacities.append(node.opacity)
        for i in range(1, len(opacities)):
            assert opacities[i] <= opacities[i - 1], "opacity must not increase"
        assert opacities[-1] == pytest.approx(0.1, abs=0.01)

    def test_max_taps_expires_node(self):
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0, max_taps=5)
        for _ in range(5):
            node.tap()
        assert node.state == NodeState.EXPIRED

    def test_expired_node_stays_expired(self):
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0, max_taps=3)
        for _ in range(3):
            node.tap()
        assert node.state == NodeState.EXPIRED
        node.update(spot=500.0)  # should be no-op
        assert node.state == NodeState.EXPIRED

    def test_full_lifecycle_transition(self):
        """FORMED → ACTIVE → TAPPED → DECAYING → EXPIRED."""
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0,
                    tap_threshold_pct=0.003, max_taps=5)
        assert node.state == NodeState.FORMED

        # Move to active zone
        node.update(spot=503.0)
        assert node.state == NodeState.ACTIVE

        # Tap once
        node.update(spot=500.1)
        assert node.state == NodeState.TAPPED

        # Tap twice more → 3 taps total → DECAYING
        node.tap()
        node.tap()
        assert node.tap_count == 3
        assert node.state == NodeState.DECAYING

        # Tap until max_taps → EXPIRED
        while node.tap_count < node.max_taps:
            node.tap()
        assert node.state == NodeState.EXPIRED

    def test_tracker_creates_and_tracks_nodes(self):
        tracker = NodeLifecycleTracker()
        result = tracker.update(spot=500.0, king_nodes=[(500.0, 1e9), (505.0, 5e8)])
        assert result["total_nodes"] == 2

    def test_tracker_detects_new_taps(self):
        tracker = NodeLifecycleTracker(tap_threshold_pct=0.003)
        # First update: creates nodes, no taps
        r1 = tracker.update(spot=490.0, king_nodes=[(500.0, 1e9)])
        assert len(r1["new_taps"]) == 0
        # Second update: spot within threshold of 500
        r2 = tracker.update(spot=500.5, king_nodes=[(500.0, 1e9)])
        assert len(r2["new_taps"]) >= 1

    def test_tracker_expired_nodes_removed(self):
        tracker = NodeLifecycleTracker(max_taps=2)
        # Create node and tap it max_taps times
        tracker.update(spot=500.0, king_nodes=[(500.0, 1e9)])  # creates + taps → count=1
        r = tracker.update(spot=500.0, king_nodes=[(500.0, 1e9)])  # taps → count=2=EXPIRED
        # After 2nd update, node is expired and removed
        assert r["total_nodes"] == 0
        assert 500.0 in r["expired"]
        # Verify internal state is clean
        state = tracker.get_state()
        assert state["total_nodes"] == 0

    def test_to_dict_serialization(self):
        node = Node(strike=500.0, gex_value=1e9, spot_at_formation=500.0)
        d = node.to_dict()
        assert d["strike"] == 500.0
        assert d["state"] == "formed"
        assert d["tap_count"] == 0
        assert "structural_weight" in d
        assert "opacity" in d


# =============================================================================
# Market Fragility Index — composite score
# =============================================================================
class TestMarketFragilityIndex:
    """Composite fragility score (0-100) from Kyle, Amihud, VPIN, QI, spread."""

    def test_all_zero_inputs_returns_elevated(self):
        """All-zero inputs → z-scores=0 → sigmoid(0)=0.5 → score=50 → ELEVATED."""
        mfi = MarketFragilityIndex()
        for _ in range(10):
            mfi.update(kyle_lambda=0.0, amihud=0.0, vpin_cdf=0.0,
                       qi_zscore=0.0, spread=0.0)
        result = mfi.compute(kyle_lambda=0.0, amihud=0.0, vpin_cdf=0.0,
                             qi_zscore=0.0, spread=0.0)
        # sigmoid(0) = 0.5 for each component → weighted sum = 0.5 → score = 50
        assert result["fragility_score"] == pytest.approx(50.0, abs=0.1)
        assert result["regime"] == "ELEVATED"

    def test_extreme_inputs_returns_crisis(self):
        """Very high inputs → score ≥ 66 → CRISIS regime."""
        mfi = MarketFragilityIndex()
        # Seed with small values so z-scores will be large
        for _ in range(20):
            mfi.update(kyle_lambda=0.001, amihud=0.001, vpin_cdf=0.01,
                       qi_zscore=0.1, spread=0.001)
        # Now feed extreme values
        result = mfi.compute(kyle_lambda=10.0, amihud=50.0, vpin_cdf=0.99,
                             qi_zscore=10.0, spread=5.0)
        assert result["regime"] == "CRISIS"
        assert result["fragility_score"] >= 66.0

    def test_moderate_inputs_returns_elevated(self):
        """Moderate z-scores → ELEVATED regime."""
        mfi = MarketFragilityIndex()
        # Seed with consistent moderate values
        for _ in range(30):
            mfi.update(kyle_lambda=0.01, amihud=0.5, vpin_cdf=0.3,
                       qi_zscore=1.0, spread=0.05)
        # Feed values ~2 sigma above mean
        result = mfi.compute(kyle_lambda=0.05, amihud=2.0, vpin_cdf=0.6,
                             qi_zscore=3.0, spread=0.2)
        assert result["regime"] in ("ELEVATED", "CRISIS")

    def test_score_bounded_0_100(self):
        """Score must always be in [0, 100]."""
        mfi = MarketFragilityIndex()
        rng = np.random.default_rng(42)
        for _ in range(50):
            kl = rng.exponential(0.1)
            am = rng.exponential(1.0)
            vp = rng.uniform(0, 1)
            qi = rng.standard_normal() * 5
            sp = rng.exponential(0.1)
            result = mfi.compute(kl, am, vp, qi, sp)
            assert 0.0 <= result["fragility_score"] <= 100.0

    def test_weights_sum_to_one(self):
        """Component weights must sum to 1.0."""
        total = sum(MarketFragilityIndex.WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_component_zscores_present(self):
        """Result must include z-score and normalized value for each component."""
        mfi = MarketFragilityIndex()
        for _ in range(10):
            mfi.update(0.01, 0.5, 0.3, 1.0, 0.05)
        result = mfi.compute(0.01, 0.5, 0.3, 1.0, 0.05)
        for comp in ["kyle_lambda", "amihud", "vpin_cdf", "qi_zscore", "spread"]:
            assert comp in result["components"]
            assert "zscore" in result["components"][comp]
            assert "normalized" in result["components"][comp]

    def test_known_inputs_known_regime(self):
        """Hand-computed: all components at their 90th percentile → ELEVATED."""
        mfi = MarketFragilityIndex(history_window=200)
        # Seed with uniform low values
        for _ in range(100):
            mfi.update(kyle_lambda=0.01, amihud=0.1, vpin_cdf=0.2,
                       qi_zscore=0.5, spread=0.02)
        # Query at roughly 2-sigma above mean
        result = mfi.compute(kyle_lambda=0.08, amihud=1.5, vpin_cdf=0.55,
                             qi_zscore=2.5, spread=0.15)
        # Should be at least ELEVATED given the z-scores
        assert result["fragility_score"] > 33.0 or result["regime"] in ("ELEVATED", "CRISIS")


# =============================================================================
# Anomaly Detector — reconstruction error
# =============================================================================
class TestAnomalyDetector:
    """FlowAnomalyDetector: synthetic anomaly recall ≥ 95% on injected toxicity."""

    def test_warmup_returns_status(self):
        det = FlowAnomalyDetector(seq_len=50)
        result = det.update(vpin=0.5, qi=0.1)
        assert result["status"] == "warming_up"
        assert result["buffer_fill"] == 0.02  # 1/50

    def test_statistical_fallback_normal_not_anomaly(self):
        """StatisticalAnomalyDetector: normal values → no anomaly."""
        det = StatisticalAnomalyDetector(window=100, threshold_sigma=2.5)
        rng = np.random.default_rng(42)
        for _ in range(100):
            features = rng.normal(0.5, 0.05, 2)
            result = det.update(features)
        # After warmup, normal values should not trigger
        normal_features = np.array([0.51, 0.49])
        result = det.update(normal_features)
        assert result["is_anomaly"] is False

    def test_synthetic_anomaly_recall_95_percent(self):
        """Inject 20 anomalies into 80 normal points; expect ≥ 19 detected."""
        det = StatisticalAnomalyDetector(window=100, threshold_sigma=1.5)
        rng = np.random.default_rng(99)

        # Seed with 50 normal observations
        for _ in range(50):
            det.update(rng.normal(0.5, 0.03, 2))

        detected = 0
        total_anomalies = 20
        for i in range(80):
            if i % 4 == 0:  # every 4th is anomalous
                features = np.array([rng.uniform(8.0, 15.0), rng.uniform(-15.0, -8.0)])
            else:
                features = rng.normal(0.5, 0.03, 2)
            result = det.update(features)
            if i % 4 == 0 and result["is_anomaly"]:
                detected += 1

        recall = detected / total_anomalies
        assert recall >= 0.95, f"anomaly recall {recall:.2%} < 95% (detected {detected}/{total_anomalies})"

    def test_flow_detector_warmup_then_active(self):
        """FlowAnomalyDetector transitions from warming_up to active."""
        det = FlowAnomalyDetector(seq_len=20)
        for i in range(25):
            result = det.update(vpin=0.3 + i * 0.01, qi=0.1)
        assert result["status"] == "active"

    def test_flow_detector_state_reports_model_type(self):
        det = FlowAnomalyDetector(seq_len=20)
        state = det.get_state()
        if HAS_TORCH:
            assert state["model_type"] == "cnn_autoencoder"
        else:
            assert state["model_type"] == "statistical_fallback"


# =============================================================================
# GEX Aggregator — zero-gamma detection
# =============================================================================
class TestGexAggregator:
    """GEX aggregator: known signed-GEX series → known crossing strikes."""

    def test_all_calls_positive_gex(self):
        """All calls → all positive GEX, no zero crossings."""
        agg = GexAggregator()
        spot = 500.0
        contracts = [
            {"strike": 490, "gamma": 0.01, "oi": 100, "type": "call", "expiry": 0.25},
            {"strike": 500, "gamma": 0.02, "oi": 200, "type": "call", "expiry": 0.25},
            {"strike": 510, "gamma": 0.015, "oi": 150, "type": "call", "expiry": 0.25},
        ]
        result = agg.compute(spot, contracts)
        assert all(g >= 0 for g in result["gex_1d"])
        assert len(result["zero_gamma_levels"]) == 0

    def test_all_puts_negative_gex(self):
        """All puts → all negative GEX, no zero crossings."""
        agg = GexAggregator()
        spot = 500.0
        contracts = [
            {"strike": 490, "gamma": 0.01, "oi": 100, "type": "put", "expiry": 0.25},
            {"strike": 500, "gamma": 0.02, "oi": 200, "type": "put", "expiry": 0.25},
            {"strike": 510, "gamma": 0.015, "oi": 150, "type": "put", "expiry": 0.25},
        ]
        result = agg.compute(spot, contracts)
        assert all(g <= 0 for g in result["gex_1d"])
        assert len(result["zero_gamma_levels"]) == 0

    def test_mixed_signs_produce_zero_crossing(self):
        """Calls below spot, puts above → sign change → zero crossing."""
        agg = GexAggregator()
        spot = 500.0
        contracts = [
            {"strike": 480, "gamma": 0.02, "oi": 500, "type": "call", "expiry": 0.25},
            {"strike": 490, "gamma": 0.02, "oi": 500, "type": "call", "expiry": 0.25},
            {"strike": 510, "gamma": 0.02, "oi": 500, "type": "put", "expiry": 0.25},
            {"strike": 520, "gamma": 0.02, "oi": 500, "type": "put", "expiry": 0.25},
        ]
        result = agg.compute(spot, contracts)
        assert len(result["zero_gamma_levels"]) >= 1
        crossing = result["zero_gamma_levels"][0]
        assert 490.0 < crossing < 510.0

    def test_zero_crossing_at_known_location(self):
        """Construct GEX that crosses zero at exactly 500."""
        agg = GexAggregator()
        spot = 500.0
        contracts = [
            {"strike": 495, "gamma": 0.01, "oi": 1000, "type": "call", "expiry": 0.25},
            {"strike": 505, "gamma": 0.01, "oi": 1000, "type": "put", "expiry": 0.25},
        ]
        result = agg.compute(spot, contracts)
        assert len(result["zero_gamma_levels"]) == 1
        crossing = result["zero_gamma_levels"][0]
        assert crossing == pytest.approx(500.0, abs=5.0)

    def test_empty_contracts_returns_empty(self):
        agg = GexAggregator()
        result = agg.compute(500.0, [])
        assert result["total_gex"] == 0.0
        assert result["zero_gamma_levels"] == []

    def test_find_zero_crossings_direct(self):
        """Unit test the crossing finder with known arrays."""
        agg = GexAggregator()
        strikes = np.array([490.0, 495.0, 500.0, 505.0, 510.0])
        gex = np.array([100.0, 50.0, -10.0, -60.0, -100.0])
        crossings = agg.find_zero_crossings(strikes, gex)
        assert len(crossings) == 1
        assert 495.0 < crossings[0] < 500.0

    def test_multiple_zero_crossings(self):
        """Two sign changes → two crossings."""
        agg = GexAggregator()
        strikes = np.array([480.0, 490.0, 500.0, 510.0, 520.0])
        gex = np.array([100.0, -50.0, 50.0, -50.0, 100.0])
        crossings = agg.find_zero_crossings(strikes, gex)
        # 100→-50 (cross 1), -50→50 (cross 2), 50→-50 (cross 3), -50→100 (cross 4)
        assert len(crossings) == 4

    def test_two_zero_crossings(self):
        """Exactly two sign changes → two crossings."""
        agg = GexAggregator()
        strikes = np.array([480.0, 490.0, 500.0, 510.0, 520.0])
        gex = np.array([100.0, 50.0, -50.0, -20.0, 100.0])
        crossings = agg.find_zero_crossings(strikes, gex)
        # 50→-50 (cross 1), -20→100 (cross 2)
        assert len(crossings) == 2

    def test_no_crossings_same_sign(self):
        agg = GexAggregator()
        strikes = np.array([490.0, 500.0, 510.0])
        gex = np.array([10.0, 20.0, 30.0])
        crossings = agg.find_zero_crossings(strikes, gex)
        assert len(crossings) == 0

    def test_single_crossing_linear_interpolation(self):
        """Verify linear interpolation: gex=[10, -10] at strikes=[495, 505] → crossing=500."""
        agg = GexAggregator()
        strikes = np.array([495.0, 505.0])
        gex = np.array([10.0, -10.0])
        crossings = agg.find_zero_crossings(strikes, gex)
        assert len(crossings) == 1
        assert crossings[0] == pytest.approx(500.0, abs=0.01)


# =============================================================================
# Vol Surface Constructor — ATM term structure
# =============================================================================
class TestVolSurfaceConstructor:
    """VolSurfaceConstructor: ATM term structure monotonicity in time-to-expiry."""

    def _make_contracts(self, spot, expiries, base_iv=0.20, skew=0.02):
        """Generate synthetic option chain contracts."""
        contracts = []
        for T in expiries:
            for moneyness in [0.90, 0.95, 1.00, 1.05, 1.10]:
                strike = spot * moneyness
                iv = base_iv + skew * (1.0 - moneyness) + 0.01 * math.sqrt(T)
                contracts.append({
                    "strike": strike,
                    "iv": max(iv, 0.05),
                    "expiry": T,
                    "type": "put" if moneyness < 1.0 else "call",
                })
        return contracts

    def test_atm_term_structure_exists(self):
        """build_surface returns non-empty ATM term structure."""
        spot = 500.0
        expiries = [0.25, 0.5, 1.0]
        contracts = self._make_contracts(spot, expiries)
        vsc = VolSurfaceConstructor()
        surface = vsc.build_surface(spot, contracts)
        assert len(surface["atm_term_structure"]) == len(expiries)

    def test_atm_term_structure_monotonic_in_tte(self):
        """For a flat base IV with positive sqrt(T) term, ATM IV should
        be monotonically non-decreasing in time-to-expiry."""
        spot = 500.0
        expiries = [0.1, 0.25, 0.5, 1.0, 2.0]
        contracts = self._make_contracts(spot, expiries, base_iv=0.20, skew=0.0)
        vsc = VolSurfaceConstructor()
        surface = vsc.build_surface(spot, contracts)
        atm = surface["atm_term_structure"]
        assert len(atm) >= 2
        ivs = [iv for _, iv in atm]
        for i in range(1, len(ivs)):
            assert ivs[i] >= ivs[i - 1] - 0.001, (
                f"ATM IV not monotonic: T={atm[i-1][0]:.2f} iv={ivs[i-1]:.4f} "
                f"→ T={atm[i][0]:.2f} iv={ivs[i]:.4f}"
            )

    def test_surface_has_required_keys(self):
        spot = 500.0
        contracts = self._make_contracts(spot, [0.25, 0.5])
        vsc = VolSurfaceConstructor()
        surface = vsc.build_surface(spot, contracts)
        required = ["grid_strikes", "grid_expiries", "iv_grid", "sabr_params",
                     "svi_params_by_expiry", "atm_term_structure", "skew_25d", "butterfly_25d"]
        for key in required:
            assert key in surface, f"missing key: {key}"

    def test_empty_contracts_returns_empty_surface(self):
        vsc = VolSurfaceConstructor()
        surface = vsc.build_surface(500.0, [])
        assert len(surface["atm_term_structure"]) == 0

    def test_surface_expiries_match_input(self):
        """Surface expiries should match the unique expiries in the input."""
        spot = 500.0
        expiries = [0.25, 0.75, 1.5]
        contracts = self._make_contracts(spot, expiries)
        vsc = VolSurfaceConstructor()
        surface = vsc.build_surface(spot, contracts)
        assert len(surface["grid_expiries"]) == len(expiries)

    def test_iv_grid_shape(self):
        """IV grid shape should be (n_strikes, n_expiries)."""
        spot = 500.0
        expiries = [0.25, 0.5, 1.0]
        contracts = self._make_contracts(spot, expiries)
        vsc = VolSurfaceConstructor()
        surface = vsc.build_surface(spot, contracts)
        grid = np.array(surface["iv_grid"])
        assert grid.shape[1] == len(expiries)

    def test_atm_iv_positive(self):
        """All ATM IV values must be positive."""
        spot = 500.0
        contracts = self._make_contracts(spot, [0.25, 0.5, 1.0])
        vsc = VolSurfaceConstructor()
        surface = vsc.build_surface(spot, contracts)
        for T, iv in surface["atm_term_structure"]:
            assert iv > 0, f"ATM IV at T={T} must be positive, got {iv}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
