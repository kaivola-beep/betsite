"""Tests for the Plackett-Luce model and calibration layer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from toto_optimizer.data.loaders import generate_demo_card, race_card_to_dataframe
from toto_optimizer.features.engineering import build_features
from toto_optimizer.models.calibration import (
    brier_score,
    expected_calibration_error,
    log_loss_score,
)
from toto_optimizer.models.predict import (
    PlackettLuceModel,
    ensure_prob_normalised,
)


def test_predicted_probabilities_sum_to_one_per_race():
    card = generate_demo_card(n_races=3, seed=1)
    feats = build_features(race_card_to_dataframe(card))
    pl = PlackettLuceModel()
    probs = pl.predict_probabilities(feats)
    probs = ensure_prob_normalised(probs)
    for _, g in probs.groupby("race_id"):
        assert g["prob"].sum() == pytest.approx(1.0, abs=1e-9)
        assert (g["prob"] > 0).all()


def test_metrics_sanity():
    p = np.array([0.9, 0.1, 0.3, 0.7, 0.5])
    y = np.array([1, 0, 0, 1, 1])
    assert 0.0 <= brier_score(p, y) <= 1.0
    assert log_loss_score(p, y) >= 0.0
    assert 0.0 <= expected_calibration_error(p, y, n_bins=3) <= 1.0


def test_strong_horse_gets_higher_probability():
    """If we manually crank a horse's speed rating, its win probability
    should increase relative to identical twins."""
    card = generate_demo_card(n_races=1, seed=3)
    long_df = race_card_to_dataframe(card)
    feats = build_features(long_df)
    pl = PlackettLuceModel()
    baseline = pl.predict_probabilities(feats).set_index("program_number")["prob"]

    # Boost horse #1's features
    boosted = feats.copy()
    mask = boosted["program_number"] == 1
    boosted.loc[mask, ["form_index", "speed_rating_f", "class_rating_f"]] += 3.0
    boost = pl.predict_probabilities(boosted).set_index("program_number")["prob"]
    assert boost[1] > baseline[1]
