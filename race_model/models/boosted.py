"""Boosted head.

The V1 implementation uses a *point-wise* classifier (``is_winner``) as
its learning objective and then converts its output to race-aware win
probabilities via a per-race softmax on logits. This matters because:

* a point-wise classifier trained on ``is_winner`` learns a calibrated
  probability only in the marginal sense; applying softmax within a race
  re-normalises the scores into a proper per-race PMF that sums to 1;
* we can apply this on top of any monotone scorer (sklearn's
  ``HistGradientBoostingClassifier``, LightGBM/XGBoost, neural net, ...)
  without changing the downstream interface.

The class transparently uses LightGBM LambdaRank when available
(``backend='lightgbm'`` or ``'auto'``) and falls back to
``HistGradientBoostingClassifier`` — both produce usable probabilities
for V1 with no extra dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from ..config import SETTINGS
from ..features import NO_MARKET_FEATURE_COLS


Backend = Literal["lightgbm", "sklearn", "auto"]


@dataclass
class GradientBoostedHead:
    feature_cols: list[str] = field(default_factory=lambda: list(NO_MARKET_FEATURE_COLS))
    backend: Backend = SETTINGS.boosted_backend    # "auto" | "lightgbm" | "sklearn"
    max_iter: int = SETTINGS.boosted_max_iter
    learning_rate: float = SETTINGS.boosted_learning_rate
    max_depth: int | None = SETTINGS.boosted_max_depth
    _model: object | None = None
    _used_backend: str | None = None

    # ------------------------------------------------------------------
    def _select_backend(self) -> str:
        if self.backend == "sklearn":
            return "sklearn"
        if self.backend == "lightgbm":
            return "lightgbm"
        # auto
        try:
            import lightgbm  # noqa: F401
            return "lightgbm"
        except ImportError:
            return "sklearn"

    # ------------------------------------------------------------------
    def fit(self, df: pd.DataFrame) -> "GradientBoostedHead":
        self._used_backend = self._select_backend()

        if self._used_backend == "lightgbm":
            self._fit_lightgbm(df)
        else:
            self._fit_sklearn(df)
        return self

    def _fit_sklearn(self, df: pd.DataFrame) -> None:
        X = df[self.feature_cols].to_numpy(dtype=float)
        y = (df["finished_position"].to_numpy() == 1).astype(int)
        # Each race should contribute equally regardless of its size
        n_r = df.groupby("race_id")["program_number"].transform("count").to_numpy()
        sample_weight = 1.0 / np.clip(n_r, 1, None)
        self._model = HistGradientBoostingClassifier(
            max_iter=self.max_iter,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            class_weight="balanced",
        )
        self._model.fit(X, y, sample_weight=sample_weight)

    def _fit_lightgbm(self, df: pd.DataFrame) -> None:
        import lightgbm as lgb  # type: ignore
        df = df.sort_values("race_id", kind="mergesort")
        X = df[self.feature_cols].to_numpy(dtype=float)
        y = (df["finished_position"].to_numpy() == 1).astype(int)
        groups = df.groupby("race_id", sort=False).size().to_numpy()
        dset = lgb.Dataset(X, label=y, group=groups)
        params = {
            "objective": "lambdarank",
            "metric": "ndcg",
            "learning_rate": self.learning_rate,
            "max_depth": -1 if self.max_depth is None else self.max_depth,
            "verbose": -1,
        }
        self._model = lgb.train(params, dset, num_boost_round=self.max_iter)

    # ------------------------------------------------------------------
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df[["race_id", "program_number", "horse_id"]].copy()
        if self._model is None:
            n = df.groupby("race_id")["program_number"].transform("count")
            out["p_boosted"] = 1.0 / n
            out["logit_boosted"] = 0.0
            return out

        X = df[self.feature_cols].to_numpy(dtype=float)
        if self._used_backend == "lightgbm":
            scores = self._model.predict(X)
        else:
            probs = self._model.predict_proba(X)[:, 1]
            probs = np.clip(probs, 1e-6, 1 - 1e-6)
            scores = np.log(probs / (1 - probs))

        out["logit_boosted"] = scores
        out["p_boosted"] = out.groupby("race_id")["logit_boosted"].transform(_softmax)
        return out


def _softmax(s: pd.Series) -> pd.Series:
    v = s.to_numpy(dtype=float)
    v = v - v.max()
    e = np.exp(v)
    return pd.Series(e / e.sum(), index=s.index)
