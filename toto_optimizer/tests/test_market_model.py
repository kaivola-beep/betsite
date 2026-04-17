"""Tests for the pool / market model."""
from __future__ import annotations

import numpy as np
import pytest

from toto_optimizer.pool.market_model import MarketModel


def test_implied_probabilities_sum_to_one():
    mm = MarketModel()
    pi = mm.implied_probabilities(np.array([0.50, 0.20, 0.15, 0.10, 0.05]))
    assert pi.sum() == pytest.approx(1.0, abs=1e-9)
    assert np.all(pi > 0)


def test_shin_moves_mass_away_from_favourite():
    """Shin debiasing should reduce the favourite's implied probability
    relative to the raw pool share (favourite-longshot bias correction)."""
    raw = np.array([0.60, 0.20, 0.10, 0.06, 0.04])
    mm_shin = MarketModel(shin=True)
    mm_flat = MarketModel(shin=False)
    pi_shin = mm_shin.implied_probabilities(raw)
    pi_flat = mm_flat.implied_probabilities(raw)
    assert pi_shin[0] <= pi_flat[0] + 1e-9
    # longshot's implied probability should be at least as high
    assert pi_shin[-1] >= pi_flat[-1] - 1e-9


def test_combo_popularity_multiplies_shares():
    mm = MarketModel(chalk_correlation=0.0)
    shares_per_leg = [
        {1: 0.3, 2: 0.2, 3: 0.5},
        {1: 0.4, 2: 0.6},
    ]
    assert mm.combo_popularity(shares_per_leg, (1, 1)) == pytest.approx(0.3 * 0.4)
    assert mm.combo_popularity(shares_per_leg, (3, 2)) == pytest.approx(0.5 * 0.6)


def test_chalk_correlation_lifts_favourites():
    mm = MarketModel(chalk_correlation=0.5)
    shares_per_leg = [
        {1: 0.5, 2: 0.1, 3: 0.4},     # 1 and 3 are top-3
        {1: 0.5, 2: 0.3, 3: 0.2},
    ]
    base = 0.5 * 0.5
    lifted = mm.combo_popularity(shares_per_leg, (1, 1))
    assert lifted > base
