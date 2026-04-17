"""Tests for the pool / market model."""
from __future__ import annotations

import numpy as np
import pytest

from toto_optimizer.pool.market_model import MarketModel


def test_none_method_is_identity():
    mm = MarketModel(method="none")
    raw = np.array([0.50, 0.20, 0.15, 0.10, 0.05])
    pi = mm.implied_probabilities(raw)
    assert pi.sum() == pytest.approx(1.0, abs=1e-9)
    assert np.allclose(pi, raw / raw.sum(), atol=1e-9)


def test_power_alpha_below_one_pulls_mass_from_favourite():
    raw = np.array([0.60, 0.20, 0.10, 0.06, 0.04])
    mm = MarketModel(method="power", power_alpha=0.85)
    pi = mm.implied_probabilities(raw)
    assert pi.sum() == pytest.approx(1.0, abs=1e-9)
    assert pi[0] < raw[0]
    assert pi[-1] > raw[-1]


def test_power_alpha_one_is_identity():
    mm = MarketModel(method="power", power_alpha=1.0)
    raw = np.array([0.4, 0.3, 0.2, 0.1])
    pi = mm.implied_probabilities(raw)
    assert np.allclose(pi, raw, atol=1e-9)


def test_shin_option_available_and_sums_to_one():
    mm = MarketModel(method="shin")
    pi = mm.implied_probabilities(np.array([0.60, 0.20, 0.10, 0.06, 0.04]))
    assert pi.sum() == pytest.approx(1.0, abs=1e-9)


def test_calibrate_power_alpha_prefers_smaller_than_one_when_longshots_win_often():
    rng = np.random.default_rng(0)
    # Simulate a world where true probability is a power of the share (alpha=0.8)
    shares_list, winners = [], []
    for _ in range(400):
        k = rng.integers(6, 12)
        q = rng.dirichlet(np.ones(k) * 1.2)
        true = q ** 0.8
        true = true / true.sum()
        w = int(rng.choice(k, p=true))
        shares_list.append(q)
        winners.append(w)
    alpha_hat = MarketModel.calibrate_power_alpha(shares_list, winners)
    assert 0.70 <= alpha_hat <= 0.95


def test_edge_table_has_expected_columns():
    import pandas as pd
    model_probs = pd.DataFrame({"race_id": ["R1", "R1"],
                                 "program_number": [1, 2],
                                 "prob": [0.6, 0.4]})
    market_probs = pd.DataFrame({"race_id": ["R1", "R1"],
                                  "program_number": [1, 2],
                                  "p_market": [0.5, 0.5]})
    t = MarketModel.edge_table(model_probs, market_probs)
    for col in ("edge", "log_edge", "fair_odds", "market_odds"):
        assert col in t.columns
