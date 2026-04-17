"""Plackett-Luce / softmax winning-probability model.

Mathematically:

    Given features x_i for runner i in a race, the winning probability is
    the softmax

        P(i wins) = exp(beta^T x_i) / sum_j exp(beta^T x_j)

    This is the Plackett-Luce likelihood restricted to the first place.
    With a small L2 ridge penalty the fit is always well-defined; without
    training data we fall back to a sensible prior that equally weights the
    most obviously predictive features. The prior yields reasonable
    probabilities even before any historical data is available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..features.engineering import FEATURE_COLS
from ..app.config import SETTINGS


@dataclass
class PlackettLuceModel:
    """Softmax / multinomial-logit model fit on (race, winner) pairs."""

    feature_cols: list[str] = field(default_factory=lambda: list(FEATURE_COLS))
    beta: np.ndarray | None = None
    ridge: float = SETTINGS.pl_ridge

    # ------------------------------------------------------------------
    # Fit / predict
    # ------------------------------------------------------------------
    def fit(self, df: pd.DataFrame, *, winner_col: str = "finished_position",
            sample_weight: np.ndarray | None = None) -> "PlackettLuceModel":
        """Fit on a DataFrame containing historical races.

        The winner is the row with ``finished_position == 1`` within each
        ``race_id``. Races where no winner is known are ignored.
        """
        groups = df.groupby("race_id", sort=False)
        races: list[tuple[np.ndarray, int]] = []
        weights: list[float] = []
        for i, (rid, g) in enumerate(groups):
            if winner_col not in g:
                continue
            winners = g.index[g[winner_col] == 1].tolist()
            if not winners:
                continue
            X = g[self.feature_cols].to_numpy(dtype=float)
            win_idx = g.index.get_indexer(winners)[0]
            races.append((X, int(win_idx)))
            weights.append(1.0 if sample_weight is None else float(sample_weight[i]))

        if not races:
            # No training data -> fall back to a sensible prior
            self.beta = _prior_beta(self.feature_cols)
            return self

        ws = np.asarray(weights, dtype=float)
        ws /= ws.sum()

        def nll(beta: np.ndarray) -> tuple[float, np.ndarray]:
            total = 0.0
            grad = np.zeros_like(beta)
            for (X, w_idx), w in zip(races, ws):
                logits = X @ beta
                m = logits.max()
                e = np.exp(logits - m)
                Z = e.sum()
                p = e / Z
                total -= w * (logits[w_idx] - (m + np.log(Z)))
                grad -= w * (X[w_idx] - p @ X)
            total += 0.5 * self.ridge * np.dot(beta, beta)
            grad += self.ridge * beta
            return total, grad

        x0 = _prior_beta(self.feature_cols)
        res = minimize(nll, x0, jac=True, method="L-BFGS-B",
                       options={"maxiter": SETTINGS.pl_max_iter,
                                "ftol": SETTINGS.pl_tol})
        self.beta = res.x
        return self

    def predict_probabilities(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a DataFrame with (race_id, program_number, prob)."""
        if self.beta is None:
            self.beta = _prior_beta(self.feature_cols)
        X = df[self.feature_cols].to_numpy(dtype=float)
        logits = X @ self.beta
        out = df[["race_id", "program_number"]].copy()
        out["logit"] = logits
        out["prob"] = out.groupby("race_id")["logit"].transform(_softmax)
        return out

    # ------------------------------------------------------------------
    def summary(self) -> pd.DataFrame:
        beta = self.beta if self.beta is not None else _prior_beta(self.feature_cols)
        return pd.DataFrame({"feature": self.feature_cols, "coef": beta})


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _softmax(x: pd.Series) -> pd.Series:
    v = x.to_numpy(dtype=float)
    v = v - v.max()
    e = np.exp(v)
    return pd.Series(e / e.sum(), index=x.index)


def _prior_beta(feature_cols: Iterable[str]) -> np.ndarray:
    """Reasonable default coefficients used when no training data exists.

    These priors encode widely-accepted directional effects (higher speed
    rating is better, worse form is worse, outer post is worse, etc.) and
    are z-scaled so that the softmax output is well-behaved.
    """
    prior = {
        "form_index": 0.9,          # already sign-corrected (higher = better)
        "speed_index": 0.6,
        "earnings_index": 0.4,
        "class_rating_f": 0.8,
        "speed_rating_f": 0.9,
        "stamina_rating_f": 0.3,
        "post_penalty": 0.5,        # already sign-corrected
        "gallop_risk_f": 0.5,       # already sign-corrected
        "layoff_penalty": 0.2,
        "equipment_delta": 0.05,
        "shoeing_delta": 0.05,
    }
    return np.array([prior.get(c, 0.0) for c in feature_cols], dtype=float)


def ensure_prob_normalised(df: pd.DataFrame, prob_col: str = "prob") -> pd.DataFrame:
    """Enforce that probabilities within each race sum exactly to 1."""
    df = df.copy()
    df[prob_col] = df.groupby("race_id")[prob_col].transform(lambda s: s / s.sum())
    return df
