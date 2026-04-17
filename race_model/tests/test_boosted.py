"""Tests for the gradient-boosted head."""
from __future__ import annotations

import pytest

from race_model.data.loaders import generate_history
from race_model.features import build_features
from race_model.models.boosted import GradientBoostedHead


def test_boosted_predictions_sum_to_one_per_race():
    df = generate_history(n_races=60, seed=11)
    feats = build_features(df)
    model = GradientBoostedHead(backend="sklearn", max_iter=50).fit(feats)
    pred = model.predict(feats)
    for _, g in pred.groupby("race_id"):
        assert g["p_boosted"].sum() == pytest.approx(1.0, abs=1e-9)


def test_boosted_backend_auto_resolves():
    df = generate_history(n_races=30, seed=12)
    feats = build_features(df)
    model = GradientBoostedHead(backend="auto", max_iter=30).fit(feats)
    assert model._used_backend in {"lightgbm", "sklearn"}
    pred = model.predict(feats)
    assert "p_boosted" in pred.columns
