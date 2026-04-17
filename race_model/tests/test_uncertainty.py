"""Race-level bootstrap uncertainty tests."""
from __future__ import annotations

import numpy as np

from race_model.data.loaders import generate_history
from race_model.features import build_features
from race_model.models.baseline import PlackettLuceBaseline
from race_model.models.uncertainty import BootstrapUncertainty


def test_bootstrap_produces_nontrivial_spread():
    df = generate_history(n_races=70, seed=20)
    feats = build_features(df)
    # Hold out the last 10 races as evaluation target
    eval_races = feats["race_id"].unique()[-10:]
    train = feats[~feats["race_id"].isin(eval_races)]
    evald = feats[feats["race_id"].isin(eval_races)]

    bs = BootstrapUncertainty(factory=lambda: PlackettLuceBaseline(),
                               n=8, prob_col="p_baseline", seed=1)
    bs.fit(train)
    draws = bs.predict_draws(evald)
    assert draws.shape == (8, len(evald))
    # At least some horses should have nonzero spread across bootstrap draws
    spread = draws.std(axis=0)
    assert (spread > 1e-4).sum() > 0


def test_bootstrap_summary_columns():
    df = generate_history(n_races=60, seed=21)
    feats = build_features(df)
    bs = BootstrapUncertainty(factory=lambda: PlackettLuceBaseline(),
                               n=4, prob_col="p_baseline", seed=1)
    bs.fit(feats)
    draws = bs.predict_draws(feats)
    summary = bs.summarise(draws, feats)
    for c in ("p_mean", "p_sd", "p_p05", "p_p95"):
        assert c in summary.columns
    # p_mean should sum to 1 within each race
    for _, g in summary.groupby("race_id"):
        assert abs(g["p_mean"].sum() - 1.0) < 1e-9
