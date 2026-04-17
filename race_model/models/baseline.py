"""Plackett-Luce / multinomial-logit baseline.

For race ``r`` with runners ``1..n_r`` and features ``x_i``, the model is

    P(i wins race r) = exp(beta . x_i) / sum_j exp(beta . x_j)

This is the Plackett-Luce likelihood restricted to the first place.
Training maximises the winner log-likelihood across races, with a small
L2 ridge for numerical stability and weak regularisation.

The baseline is race-aware by construction (softmax is applied per
race) and its outputs always sum to 1 within a race.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..config import SETTINGS
from ..features import FEATURE_COLS, NO_MARKET_FEATURE_COLS


@dataclass
class PlackettLuceBaseline:
    feature_cols: list[str] = field(default_factory=lambda: list(NO_MARKET_FEATURE_COLS))
    ridge: float = SETTINGS.pl_ridge
    beta: np.ndarray | None = None

    # ------------------------------------------------------------------
    def fit(self, df: pd.DataFrame, *, sample_weight: np.ndarray | None = None) -> "PlackettLuceBaseline":
        races: list[tuple[np.ndarray, int]] = []
        for _, g in df.groupby("race_id", sort=False):
            if "finished_position" not in g:
                continue
            w_idx = np.where(g["finished_position"].to_numpy() == 1)[0]
            if len(w_idx) == 0:
                continue
            X = g[self.feature_cols].to_numpy(dtype=float)
            races.append((X, int(w_idx[0])))
        if not races:
            self.beta = np.zeros(len(self.feature_cols))
            return self

        def nll(beta: np.ndarray):
            total = 0.0
            grad = np.zeros_like(beta)
            for X, w in races:
                logits = X @ beta
                m = logits.max()
                e = np.exp(logits - m)
                Z = e.sum()
                p = e / Z
                total -= logits[w] - (m + np.log(Z))
                grad -= X[w] - p @ X
            total /= len(races)
            grad /= len(races)
            total += 0.5 * self.ridge * np.dot(beta, beta)
            grad += self.ridge * beta
            return total, grad

        x0 = np.zeros(len(self.feature_cols))
        res = minimize(nll, x0, jac=True, method="L-BFGS-B",
                       options={"maxiter": SETTINGS.pl_max_iter, "ftol": SETTINGS.pl_tol})
        self.beta = res.x
        return self

    # ------------------------------------------------------------------
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return per-row probabilities summing to 1 within each race."""
        if self.beta is None:
            self.beta = np.zeros(len(self.feature_cols))
        X = df[self.feature_cols].to_numpy(dtype=float)
        logits = X @ self.beta
        out = df[["race_id", "program_number", "horse_id"]].copy()
        out["logit_baseline"] = logits
        out["p_baseline"] = out.groupby("race_id")["logit_baseline"].transform(_softmax)
        return out

    # ------------------------------------------------------------------
    def coef_table(self) -> pd.DataFrame:
        b = self.beta if self.beta is not None else np.zeros(len(self.feature_cols))
        return pd.DataFrame({"feature": self.feature_cols, "coef": b}).sort_values(
            "coef", key=lambda s: s.abs(), ascending=False
        )


def _softmax(s: pd.Series) -> pd.Series:
    v = s.to_numpy(dtype=float)
    v = v - v.max()
    e = np.exp(v)
    return pd.Series(e / e.sum(), index=s.index)
