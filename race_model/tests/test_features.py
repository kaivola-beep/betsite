"""Race-aware feature engineering tests."""
from __future__ import annotations

import numpy as np

from race_model.data.loaders import generate_history
from race_model.features import FEATURE_COLS, build_features


def test_features_zscored_within_race():
    df = generate_history(n_races=10, seed=1)
    feats = build_features(df)
    # At least two continuous z-score columns should have near-zero mean
    for c in ("form_index_z", "speed_rating_z", "class_rating_z"):
        assert c in feats
        means = feats.groupby("race_id")[c].mean().to_numpy()
        assert np.allclose(means, 0.0, atol=1e-7)


def test_missingness_flag_set_when_rating_missing():
    df = generate_history(n_races=5, seed=2).copy()
    df.loc[df.index[:5], "speed_rating"] = np.nan
    feats = build_features(df)
    flagged = feats["missing_speed_rating"].to_numpy()
    assert flagged.sum() >= 5


def test_feature_cols_all_present():
    df = generate_history(n_races=10, seed=3)
    feats = build_features(df)
    for c in FEATURE_COLS:
        assert c in feats.columns
