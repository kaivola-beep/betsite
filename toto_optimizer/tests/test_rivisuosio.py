"""Tests for combination-popularity models."""
from __future__ import annotations

import numpy as np
import pytest

from toto_optimizer.pool.rivisuosio import (
    ChalkCorrelationModel,
    IndependenceModel,
    LogLinearModel,
)


def _shares():
    return [
        {1: 0.50, 2: 0.30, 3: 0.15, 4: 0.05},
        {1: 0.40, 2: 0.35, 3: 0.20, 4: 0.05},
        {1: 0.45, 2: 0.30, 3: 0.15, 4: 0.10},
    ]


def test_independence_is_product_of_shares():
    m = IndependenceModel()
    s = _shares()
    assert m.popularity((1, 1, 1), s) == pytest.approx(0.5 * 0.4 * 0.45)
    assert m.popularity((4, 4, 4), s) == pytest.approx(0.05 * 0.05 * 0.10)


def test_chalk_lifts_only_favourite_combos():
    base = IndependenceModel().popularity((1, 1, 1), _shares())
    chalk = ChalkCorrelationModel(alpha=0.5, top_m=2).popularity((1, 1, 1), _shares())
    assert chalk > base

    # Longshot combo: none of the picks are in the top 2 favourites, so
    # the chalk model should give exactly the independence popularity.
    ls_base = IndependenceModel().popularity((4, 4, 4), _shares())
    ls_chalk = ChalkCorrelationModel(alpha=0.5, top_m=2).popularity((4, 4, 4), _shares())
    assert ls_chalk == pytest.approx(ls_base)


def test_log_linear_fit_recovers_constant_when_observations_match_independence():
    """If observed shares equal the independence baseline, theta should be 0."""
    s = _shares()
    combos = [(1, 1, 1), (2, 2, 2), (3, 3, 3)]
    obs = [(c, IndependenceModel().popularity(c, s)) for c in combos]
    m = LogLinearModel(top_m=2).fit(obs, s)
    # const is unconstrained but should be close to 0; theta should be ~0
    assert np.allclose(m.theta, 0.0, atol=1e-6)
    assert abs(m.const) < 1e-6


def test_log_linear_predicts_lift_when_fit_on_lifted_data():
    """Construct observations that include a +0.3 per-top-M chalk lift in
    every leg, fit the log-linear model, and check it recovers it."""
    s = _shares()
    combos = [(1, 1, 1), (1, 2, 1), (2, 2, 2), (2, 3, 1),
              (3, 3, 3), (4, 4, 4), (1, 3, 2), (2, 1, 2)]
    rows = []
    for c in combos:
        indep = IndependenceModel().popularity(c, s)
        fav_hits = 0
        for k, n in enumerate(c):
            top = sorted(s[k].values(), reverse=True)[:2]
            if s[k][n] in top:
                fav_hits += 1
        r = indep * np.exp(0.3 * fav_hits)
        rows.append((c, r))
    m = LogLinearModel(top_m=2).fit(rows, s)
    # Each theta should be close to 0.3
    assert np.allclose(m.theta, 0.3, atol=1e-6)
