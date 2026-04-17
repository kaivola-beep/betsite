"""Calibration methods for race-aware probabilistic forecasts.

Two methods are provided; they can be chained:

* :class:`TemperatureScaler` – fits a single scalar temperature ``T`` that
  divides logits before the per-race softmax. ``T > 1`` softens the
  distribution, ``T < 1`` sharpens it. Fit on out-of-fold data via
  log-loss minimisation. Preserves the per-race sum-to-one by
  construction.
* :class:`IsotonicWithRenorm` – applies a marginal isotonic regression
  to individual win probabilities and *then* re-normalises within each
  race so the outputs remain a valid PMF. Useful for correcting local
  miscalibration that temperature scaling cannot fix.

Both classes implement the same API: ``.fit(df, y, prob_col)`` and
``.transform(df, prob_col)``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.isotonic import IsotonicRegression

from ..config import SETTINGS


def _race_renormalise(df: pd.DataFrame, prob_col: str) -> pd.DataFrame:
    df = df.copy()
    df[prob_col] = df.groupby("race_id")[prob_col].transform(lambda s: s / s.sum())
    return df


# ---------------------------------------------------------------------------
# Temperature scaling
# ---------------------------------------------------------------------------

@dataclass
class TemperatureScaler:
    """Single-scalar temperature. Requires a per-row logit column.

    The input DataFrame must contain a logit column. If
    ``p_<name>`` is passed as ``prob_col`` but no logit column is present,
    a logit is derived from the probability assuming the same softmax
    structure (``logit = log p``, which is exact up to a per-race
    constant that the softmax removes).
    """
    T: float = 1.0

    def fit(self, df: pd.DataFrame, y: np.ndarray, *, prob_col: str = "p_ens") -> "TemperatureScaler":
        p = np.clip(df[prob_col].to_numpy(dtype=float), 1e-12, 1 - 1e-12)
        # Race-aware logits: log p; the softmax is invariant to a per-race
        # additive constant, so we drop the Z term here.
        logits = np.log(p)
        race_ids = df["race_id"].to_numpy()
        y = np.asarray(y, dtype=int)

        unique, inverse = np.unique(race_ids, return_inverse=True)

        def nll(T: float) -> float:
            if T <= 0:
                return 1e12
            scaled = logits / T
            # For each race, compute log-softmax
            ll = 0.0
            count = 0
            for i, rid in enumerate(unique):
                mask = inverse == i
                if not mask.any():
                    continue
                w = np.where(mask & (y == 1))[0]
                if len(w) == 0:
                    continue
                s = scaled[mask]
                m = s.max()
                ll -= s[np.where(y[mask] == 1)[0][0]] - (m + np.log(np.exp(s - m).sum()))
                count += 1
            return ll / max(count, 1)

        lo, hi = SETTINGS.temperature_bounds
        res = minimize_scalar(nll, bounds=(lo, hi), method="bounded",
                               options={"xatol": 1e-4})
        self.T = float(res.x)
        return self

    def transform(self, df: pd.DataFrame, *, prob_col: str = "p_ens") -> pd.DataFrame:
        df = df.copy()
        p = np.clip(df[prob_col].to_numpy(dtype=float), 1e-12, 1 - 1e-12)
        scaled_logits = np.log(p) / self.T
        df["__scaled_logit"] = scaled_logits
        df[prob_col] = df.groupby("race_id")["__scaled_logit"].transform(_stable_softmax)
        return df.drop(columns=["__scaled_logit"])


# ---------------------------------------------------------------------------
# Marginal isotonic + re-normalisation
# ---------------------------------------------------------------------------

@dataclass
class IsotonicWithRenorm:
    """Isotonic calibration of marginal win probabilities, then
    per-race re-normalisation to restore a valid PMF."""
    _iso: IsotonicRegression | None = None

    def fit(self, df: pd.DataFrame, y: np.ndarray, *, prob_col: str = "p_ens") -> "IsotonicWithRenorm":
        p = np.clip(df[prob_col].to_numpy(dtype=float), 1e-6, 1 - 1e-6)
        if len(p) < 30:
            self._iso = None
            return self
        self._iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self._iso.fit(p, np.asarray(y, dtype=int))
        return self

    def transform(self, df: pd.DataFrame, *, prob_col: str = "p_ens") -> pd.DataFrame:
        df = df.copy()
        if self._iso is None:
            return _race_renormalise(df, prob_col)
        p = np.clip(df[prob_col].to_numpy(dtype=float), 1e-6, 1 - 1e-6)
        df[prob_col] = self._iso.predict(p)
        return _race_renormalise(df, prob_col)


def _stable_softmax(s: pd.Series) -> pd.Series:
    v = s.to_numpy(dtype=float)
    v = v - v.max()
    e = np.exp(v)
    return pd.Series(e / e.sum(), index=s.index)
