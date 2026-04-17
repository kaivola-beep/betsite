"""Tests for the simple scorer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ingestion.scoring import (
    ScoringWeights,
    score_bootstrap,
    score_simple,
    softmax_within_race,
)


def _toy_frame():
    return pd.DataFrame([
        {"race_id": "R1", "program_number": 1, "horse_name": "A",
         "market_share": 0.5,
         "prior_finishes": [1, 2, 1, 2, 3],
         "prior_km_times": [72.0, 71.5, 72.3, 71.8, 72.0],
         "prior_earnings": [3000, 2500, 4000, 1800, 2200],
         "prior_opponent_strengths": [],
         "days_since_last_start": 14, "gallop_risk": 0.02,
         "speed_rating": 71.0, "class_rating": 2500.0,
         "stamina_rating": 73.0},
        {"race_id": "R1", "program_number": 2, "horse_name": "B",
         "market_share": 0.3,
         "prior_finishes": [4, 5, 3, 6, 4],
         "prior_km_times": [73.5, 73.0, 73.8, 73.1, 73.4],
         "prior_earnings": [800, 400, 1000, 300, 500],
         "prior_opponent_strengths": [],
         "days_since_last_start": 22, "gallop_risk": 0.05,
         "speed_rating": 73.2, "class_rating": 500.0,
         "stamina_rating": 74.0},
        {"race_id": "R1", "program_number": 3, "horse_name": "C",
         "market_share": 0.2,
         "prior_finishes": [7, 6, 8, 7, 5],
         "prior_km_times": [75.0, 74.8, 75.1, 74.6, 75.2],
         "prior_earnings": [100, 150, 50, 120, 80],
         "prior_opponent_strengths": [],
         "days_since_last_start": 38, "gallop_risk": 0.08,
         "speed_rating": 74.8, "class_rating": 110.0,
         "stamina_rating": 75.5},
    ])


def test_score_simple_sums_to_one_per_race():
    out = score_simple(_toy_frame())
    assert out.groupby("race_id")["p_model"].sum().round(9).eq(1.0).all()
    assert (out["p_model"] > 0).all()


def test_score_simple_best_horse_gets_highest_prob():
    """Horse A has the best form in every metric -> should win the softmax."""
    out = score_simple(_toy_frame())
    order = out.sort_values("p_model", ascending=False)["program_number"].tolist()
    assert order[0] == 1


def test_score_simple_has_edge_column_when_market_present():
    out = score_simple(_toy_frame())
    assert "edge" in out.columns
    assert "p_market_implied" in out.columns


def test_score_bootstrap_produces_quantile_columns():
    out = score_bootstrap(_toy_frame(), n_boot=15, seed=1)
    for c in ("p_model_mean", "p_model_sd", "p_model_p05",
               "p_model_p95", "fair_odds_conservative"):
        assert c in out.columns
    # p_model_mean should be roughly consistent with p_model
    diff = (out["p_model"] - out["p_model_mean"]).abs()
    assert diff.max() < 0.3


def test_softmax_helper_is_numerically_stable():
    s = pd.Series([1000.0, 999.0, -5.0])
    out = softmax_within_race(s)
    assert out.sum() == pytest.approx(1.0)
    assert out.iloc[0] > out.iloc[1] > out.iloc[2]


def test_weights_vector():
    w = ScoringWeights().as_vector()
    assert len(w) == 7
    assert (w > 0).all()
