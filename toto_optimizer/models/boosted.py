"""Optional gradient-boosted ranking model.

Plackett-Luce is a reasonable baseline, but if you have hundreds of
historical races and rich feature data, a LambdaRank-trained tree model
typically beats it. This module is opt-in: it imports lightgbm (or
xgboost) lazily so the rest of the package remains usable without them.

Interface mirrors :class:`models.predict.PlackettLuceModel`, so a
:class:`BoostedRankingModel` instance can drop straight into
:class:`models.ensemble.LogLinearEnsemble`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from ..features.engineering import FEATURE_COLS


Backend = Literal["lightgbm", "xgboost"]


@dataclass
class BoostedRankingModel:
    backend: Backend = "lightgbm"
    feature_cols: list[str] = field(default_factory=lambda: list(FEATURE_COLS))
    num_boost_round: int = 400
    learning_rate: float = 0.05
    max_depth: int = 6
    _model: object | None = None

    # ------------------------------------------------------------------
    def fit(self, df: pd.DataFrame, *, winner_col: str = "finished_position") -> "BoostedRankingModel":
        groups = df.groupby("race_id", sort=False)
        X_parts, y_parts, group_sizes = [], [], []
        for _, g in groups:
            if winner_col not in g:
                continue
            if not (g[winner_col] == 1).any():
                continue
            X_parts.append(g[self.feature_cols].to_numpy(dtype=float))
            y_parts.append((g[winner_col] == 1).astype(int).to_numpy())
            group_sizes.append(len(g))
        if not X_parts:
            return self
        X = np.vstack(X_parts)
        y = np.concatenate(y_parts)

        if self.backend == "lightgbm":
            import lightgbm as lgb  # type: ignore
            dset = lgb.Dataset(X, label=y, group=group_sizes)
            params = {
                "objective": "lambdarank",
                "metric": "ndcg",
                "learning_rate": self.learning_rate,
                "max_depth": self.max_depth,
                "verbose": -1,
            }
            self._model = lgb.train(params, dset, num_boost_round=self.num_boost_round)
        elif self.backend == "xgboost":
            import xgboost as xgb  # type: ignore
            dmat = xgb.DMatrix(X, label=y)
            dmat.set_group(group_sizes)
            params = {
                "objective": "rank:pairwise",
                "eta": self.learning_rate,
                "max_depth": self.max_depth,
                "verbosity": 0,
            }
            self._model = xgb.train(params, dmat, num_boost_round=self.num_boost_round)
        else:
            raise ValueError(f"Unknown backend: {self.backend}")
        return self

    # ------------------------------------------------------------------
    def predict_probabilities(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a softmax-over-logits probability per race.

        The raw tree output is a ranking score, not a probability. We
        convert it to a probability by applying a race-wise softmax over
        the scores. This preserves the ranking and produces a valid PMF
        within each race.
        """
        out = df[["race_id", "program_number"]].copy()
        if self._model is None:
            out["prob"] = 1.0 / df.groupby("race_id")["program_number"].transform("count")
            return out
        X = df[self.feature_cols].to_numpy(dtype=float)
        if self.backend == "lightgbm":
            scores = self._model.predict(X)
        else:
            import xgboost as xgb  # type: ignore
            scores = self._model.predict(xgb.DMatrix(X))
        out["logit"] = scores
        out["prob"] = out.groupby("race_id")["logit"].transform(_softmax)
        return out


def _softmax(x: pd.Series) -> pd.Series:
    v = x.to_numpy(dtype=float)
    v = v - v.max()
    e = np.exp(v)
    return pd.Series(e / e.sum(), index=x.index)
