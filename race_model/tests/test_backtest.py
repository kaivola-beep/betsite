"""Tests for walk-forward backtest."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from race_model.data.loaders import generate_history
from race_model.evaluation.backtest import walk_forward
from race_model.evaluation.diagnostics import bucketed_report
from race_model.models.stack import build_stack


def test_walk_forward_runs_and_respects_time():
    df = generate_history(n_races=200, seed=10)
    res = walk_forward(df, build_stack,
                       k_folds=3, min_train_races=80, val_size=20, test_size=30)
    assert len(res.folds) == 3
    # Each subsequent fold uses strictly later test dates
    dates = [pd.to_datetime(f["test_date_max"]) for f in res.folds]
    assert dates == sorted(dates)


def test_walk_forward_oof_contains_all_predictions():
    df = generate_history(n_races=160, seed=11)
    res = walk_forward(df, build_stack,
                       k_folds=2, min_train_races=80, val_size=10, test_size=25)
    assert res.oof_probs["p_ens"].isna().sum() == 0
    assert set(res.oof_probs["fold"].unique()) == {1, 2}


def test_bucketed_report_returns_per_bucket_metrics():
    df = generate_history(n_races=150, seed=12)
    res = walk_forward(df, build_stack,
                       k_folds=2, min_train_races=80, val_size=10, test_size=20)
    report = bucketed_report(res.oof_probs)
    assert "bucket_race_size" in report
    assert "bucket_prob" in report
    assert (report["bucket_race_size"]["n"] > 0).all()


def test_walk_forward_rejects_too_short_history():
    df = generate_history(n_races=30, seed=13)
    with pytest.raises(ValueError):
        walk_forward(df, build_stack,
                     k_folds=3, min_train_races=80, val_size=20, test_size=20)
