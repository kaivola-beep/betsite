"""Log-linear ensemble of race-normalised probability models.

Given ``K`` models that each produce a valid per-race PMF
``p_k`` and non-negative weights ``w_k`` with ``sum w_k > 0``, the
log-linear pool is

    p_ens_i proportional to prod_k p_k,i^w_k,

re-normalised within each race. This is the standard external-Bayesian
log-linear opinion pool (Genest & Zidek, 1986), preferred here over a
linear mixture because its probability estimates remain well calibrated
when individual forecasts are calibrated, and the softmax across the
logit-weighted sum is numerically stable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class LogLinearEnsemble:
    """Mixes any number of race-normalised probability columns.

    Parameters
    ----------
    weights
        Mapping from model name (e.g. "baseline") to non-negative weight.
        The keys are also used to locate the per-model probability
        columns (``f"p_{name}"``).
    """
    weights: dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def blend(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return ``df`` extended with a ``p_ens`` column."""
        if not self.weights:
            raise ValueError("Ensemble weights are empty.")

        out = df.copy()
        eps = 1e-9
        log_p = np.zeros(len(out), dtype=float)
        total_w = 0.0
        for name, w in self.weights.items():
            if w <= 0:
                continue
            col = f"p_{name}"
            if col not in out:
                continue
            log_p += w * np.log(np.clip(out[col].to_numpy(), eps, 1.0))
            total_w += w
        if total_w <= 0:
            raise ValueError("All ensemble weights evaluated to zero.")
        log_p /= total_w
        out["log_p_ens"] = log_p
        out["p_ens"] = out.groupby("race_id")["log_p_ens"].transform(_stable_softmax)
        return out.drop(columns=["log_p_ens"])


def _stable_softmax(s: pd.Series) -> pd.Series:
    v = s.to_numpy(dtype=float)
    v = v - v.max()
    e = np.exp(v)
    return pd.Series(e / e.sum(), index=s.index)
