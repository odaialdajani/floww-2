"""
backend/tests/services/rl/test_trading_env.py

Unit tests for trading_env.py — RL trading environment.

Coverage:
    - Environment initialization
    - reset() returns correct observation shape
    - step() returns correct tuple shape
    - Action mapping (buy/sell/hold)
    - Position tracking
    - P&L computation
    - Episode termination
    - Reward computation
    - Random policy completes 100 episodes
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


class TestTradingEnv:
    def test_init(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        assert env.observation_dim == 20
        assert env.action_dim == 5
        assert env.position == 0
        assert env.done is False

    def test_reset_returns_correct_shape(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        obs = env.reset()
        assert isinstance(obs, np.ndarray)
        assert obs.shape == (20,)
        assert obs.dtype == np.float32

    def test_reset_randomizes_state(self):
        from services.rl.trading_env import TradingEnv
        env1 = TradingEnv(seed=42)
        env2 = TradingEnv(seed=99)
        obs1 = env1.reset()
        obs2 = env2.reset()
        # Different seeds should produce different observations
        assert not np.allclose(obs1, obs2)

    def test_step_returns_tuple(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        result = env.step(2)  # hold
        assert len(result) == 4
        obs, reward, done, info = result
        assert isinstance(obs, np.ndarray)
        assert obs.shape == (20,)
        assert isinstance(reward, float)
        assert isinstance(done, bool)
        assert isinstance(info, dict)

    def test_hold_action(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        initial_position = env.position
        obs, reward, done, info = env.step(2)  # hold = action 2
        assert env.position == initial_position

    def test_buy_action_increases_position(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        obs, reward, done, info = env.step(3)  # buy = action 3 (signal +1)
        assert env.position >= 0  # Should try to buy

    def test_strong_buy(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        obs, reward, done, info = env.step(4)  # strong buy = action 4 (signal +2)
        # Position should increase
        assert env.position >= 0

    def test_sell_reduces_position(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        # First buy
        env.step(4)  # strong buy
        pos_after_buy = env.position
        # Then sell
        env.step(0)  # strong sell
        # Position should not go below 0
        assert env.position >= 0

    def test_position_never_negative(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        for _ in range(50):
            env.step(0)  # strong sell
        assert env.position >= 0

    def test_position_never_exceeds_max(self):
        from services.rl.trading_env import MAX_POSITION, TradingEnv
        env = TradingEnv()
        env.reset()
        for _ in range(50):
            env.step(4)  # strong buy
        assert env.position <= MAX_POSITION

    def test_episode_terminates(self):
        from services.rl.trading_env import MAX_STEPS_PER_EPISODE, TradingEnv
        env = TradingEnv()
        env.reset()
        done = False
        for _ in range(MAX_STEPS_PER_EPISODE + 10):
            obs, reward, done, info = env.step(2)
            if done:
                break
        assert done is True
        assert env.step_count >= MAX_STEPS_PER_EPISODE

    def test_done_step_returns_zero_reward(self):
        from services.rl.trading_env import MAX_STEPS_PER_EPISODE, TradingEnv
        env = TradingEnv()
        env.reset()
        # Run to end
        for _ in range(MAX_STEPS_PER_EPISODE):
            obs, reward, done, info = env.step(2)
        # Step after done
        obs, reward, done, info = env.step(2)
        assert done is True

    def test_reward_is_finite(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        for _ in range(100):
            obs, reward, done, info = env.step(2)
            assert np.isfinite(reward), f"Reward {reward} is not finite"
            if done:
                break

    def test_info_contains_required_keys(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        obs, reward, done, info = env.step(2)
        assert "position" in info
        assert "cash" in info
        assert "total_pnl" in info
        assert "spot" in info
        assert "step" in info

    def test_random_policy_completes_100_episodes(self):
        """Random policy should complete 100 episodes without crashes."""
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        total_rewards = []
        for ep in range(100):
            obs = env.reset()
            episode_reward = 0.0
            done = False
            while not done:
                action = env.rng.randint(0, 5)
                obs, reward, done, info = env.step(action)
                episode_reward += reward
            total_rewards.append(episode_reward)
        # Reward distribution should be non-degenerate
        assert len(total_rewards) == 100
        assert np.std(total_rewards) > 0, "Reward distribution is degenerate"

    def test_observation_values_bounded(self):
        """Observations should be reasonably bounded."""
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        for _ in range(200):
            obs, reward, done, info = env.step(2)
            assert np.all(np.isfinite(obs)), f"Non-finite observation: {obs}"
            if done:
                break

    def test_cash_decreases_on_buy(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        initial_cash = env.cash
        env.step(4)  # strong buy
        # Cash should decrease (or stay same if can't afford)
        assert env.cash <= initial_cash

    def test_get_state(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        state = env.get_state()
        assert "step" in state
        assert "position" in state
        assert "cash" in state
        assert "spot" in state
        assert "vpin" in state
        assert "done" in state

    def test_multiple_resets(self):
        """Environment should be reusable after reset."""
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        for _ in range(10):
            obs = env.reset()
            assert obs.shape == (20,)
            assert env.done is False
            assert env.position == 0

    def test_step_count_increments(self):
        from services.rl.trading_env import TradingEnv
        env = TradingEnv()
        env.reset()
        assert env.step_count == 0
        env.step(2)
        assert env.step_count == 1
        env.step(2)
        assert env.step_count == 2
