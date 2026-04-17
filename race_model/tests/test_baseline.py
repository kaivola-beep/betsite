"""Tests for the Plackett-Luce baseline."""
from __future__ import annotations

import numpy as np
import pytest

from race_model.data.loaders import generate_history
from race_model.features import build_features
from race_model.models.baseline import PlackettLuceBaseline


def test_probabilities_sum_to_one_per_race():
    df = generate_history(n_races=40, seed=1)
    feats = build_features(df)
    pl = PlackettLuceBaseline().fit(feats)
    pred = pl.predict(feats)
    for _, g in pred.groupby("race_id"):
        assert g["p_baseline"].sum() == pytest.approx(1.0, abs=1e-9)
        assert (g["p_baseline"] > 0).all()


def test_baseline_better_than_uniform_on_synthetic():
    df = generate_history(n_races=80, seed=2)
    feats = build_features(df)
    pl = PlackettLuceBaseline().fit(feats)
    pred = pl.predict(feats)
    merged = pred.merge(feats[["race_id", "program_number", "finished_position"]],
                         on=["race_id", "program_number"])
    p = merged["p_baseline"].to_numpy()
    y = (merged["finished_position"] == 1).astype(int).to_numpy()

    # Log-loss vs uniform (1/n) baseline
    n = merged.groupby("race_id")["program_number"].transform("count").to_numpy()
    uniform = 1.0 / n
    log_loss_model = -np.mean(y * np.log(p.clip(1e-12)) + (1 - y) * np.log((1 - p).clip(1e-12)))
    log_loss_unif = -np.mean(y * np.log(uniform) + (1 - y) * np.log(1 - uniform))
    assert log_loss_model < log_loss_unif


def test_baseline_assigns_higher_prob_to_winners_on_average():
    """Individual feature coefficients are not identifiable under strong
    multicollinearity (form/speed/class/stamina all proxy latent ability).
    But the functional claim - winners should on average be assigned
    higher probability than losers - is directly testable."""
    df = generate_history(n_races=150, seed=3)
    feats = build_features(df)
    pl = PlackettLuceBaseline().fit(feats)
    pred = pl.predict(feats).merge(
        feats[["race_id", "program_number", "finished_position"]],
        on=["race_id", "program_number"])
    winners = pred.loc[pred["finished_position"] == 1, "p_baseline"]
    losers = pred.loc[pred["finished_position"] != 1, "p_baseline"]
    assert winners.mean() > losers.mean() * 1.5
