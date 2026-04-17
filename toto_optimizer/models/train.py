"""Training pipeline with time-respecting train/validation/test split.

Usage
-----
>>> from toto_optimizer.models.train import train_from_history
>>> pipeline = train_from_history(history_df, date_col="race_date")

The function returns a :class:`ModelPipeline` with fitted Plackett-Luce
model and calibrator, plus evaluation metrics on the held-out set.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from ..app.config import SETTINGS
from ..features.engineering import build_features
from .calibration import ProbabilityCalibrator, calibration_report
from .predict import PlackettLuceModel, ensure_prob_normalised


@dataclass
class ModelPipeline:
    feature_builder_config: Optional[dict] = None
    pl_model: PlackettLuceModel = field(default_factory=PlackettLuceModel)
    calibrator: ProbabilityCalibrator = field(
        default_factory=lambda: ProbabilityCalibrator(method=SETTINGS.calibration_method)
    )
    metrics: dict = field(default_factory=dict)

    def predict(self, long_df: pd.DataFrame) -> pd.DataFrame:
        feats = build_features(long_df)
        probs = self.pl_model.predict_probabilities(feats)
        probs = self.calibrator.transform(probs)
        probs = ensure_prob_normalised(probs)
        return probs


def _time_split(df: pd.DataFrame, date_col: str,
                train_frac: float = 0.7, val_frac: float = 0.15):
    dates = np.sort(df[date_col].unique())
    n = len(dates)
    n_train = int(n * train_frac)
    n_val = int(n * val_frac)
    train_dates = set(dates[:n_train])
    val_dates = set(dates[n_train:n_train + n_val])
    test_dates = set(dates[n_train + n_val:])
    return (df[df[date_col].isin(train_dates)].copy(),
            df[df[date_col].isin(val_dates)].copy(),
            df[df[date_col].isin(test_dates)].copy())


def train_from_history(history_df: pd.DataFrame, *,
                       date_col: str = "race_date",
                       method: str = SETTINGS.calibration_method) -> ModelPipeline:
    """Fit the full pipeline on a long-format historical DataFrame.

    The input must contain at least all ``features.engineering.FEATURE_COLS``
    source columns plus ``race_id``, ``program_number``, ``finished_position``
    and ``date_col``. Rows with missing date are dropped.
    """
    df = history_df.dropna(subset=[date_col]).copy()
    train_df, val_df, test_df = _time_split(df, date_col)

    train_feats = build_features(train_df)
    val_feats = build_features(val_df) if len(val_df) else None
    test_feats = build_features(test_df) if len(test_df) else None

    pl = PlackettLuceModel().fit(train_feats)

    # --- Calibrator fit on validation (out-of-fold) probabilities ---------
    calibrator = ProbabilityCalibrator(method=method)
    if val_feats is not None and len(val_feats):
        probs = pl.predict_probabilities(val_feats)
        probs = ensure_prob_normalised(probs)
        merged = val_feats.merge(probs[["race_id", "program_number", "prob"]],
                                  on=["race_id", "program_number"])
        y = (merged["finished_position"] == 1).astype(int).to_numpy()
        calibrator.fit(merged["prob"].to_numpy(), y)

    metrics: dict = {}
    if test_feats is not None and len(test_feats):
        probs = pl.predict_probabilities(test_feats)
        probs = calibrator.transform(probs)
        probs = ensure_prob_normalised(probs)
        merged = test_feats.merge(probs[["race_id", "program_number", "prob"]],
                                   on=["race_id", "program_number"])
        y = (merged["finished_position"] == 1).astype(int).to_numpy()
        metrics["test"] = calibration_report(merged["prob"].to_numpy(), y)

    return ModelPipeline(pl_model=pl, calibrator=calibrator, metrics=metrics)
