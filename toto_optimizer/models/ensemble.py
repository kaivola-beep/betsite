"""Ensemble of a Plackett-Luce model and a market-anchored prior.

The market-anchored probability is the *debiased* pool-implied probability
(see :mod:`pool.market_model`). Blending model and market probabilities is
equivalent to a log-linear opinion pool

    p_ens_i proportional to p_model_i^w_model * p_market_i^w_market

and renormalising within each race. The log-linear pool is a standard way
of combining probabilistic forecasts and tends to outperform linear pools
when the individual forecasts are well calibrated (Genest & Zidek, 1986).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..app.config import SETTINGS


@dataclass
class LogLinearEnsemble:
    w_model: float = SETTINGS.ensemble_weights.get("plackett_luce", 0.6)
    w_market: float = SETTINGS.ensemble_weights.get("market_anchor", 0.4)

    def blend(self, model_probs: pd.DataFrame,
              market_probs: pd.DataFrame,
              prob_col_model: str = "prob",
              prob_col_market: str = "p_market") -> pd.DataFrame:
        """Return ``model_probs`` with an added ``prob_ens`` column."""
        merged = model_probs.merge(market_probs, on=["race_id", "program_number"],
                                     how="left", suffixes=("", "_m"))
        if prob_col_market not in merged:
            # No market info -> return unchanged model probs
            merged["prob_ens"] = merged[prob_col_model]
            return merged

        # Replace NaN market with model prob (graceful degradation)
        merged[prob_col_market] = merged[prob_col_market].fillna(merged[prob_col_model])

        eps = 1e-9
        log_p = (self.w_model * np.log(np.clip(merged[prob_col_model], eps, 1.0))
                 + self.w_market * np.log(np.clip(merged[prob_col_market], eps, 1.0)))
        merged["log_p_ens"] = log_p
        merged["prob_ens"] = merged.groupby("race_id")["log_p_ens"].transform(_stable_softmax)
        return merged.drop(columns=["log_p_ens"])


def _stable_softmax(x: pd.Series) -> pd.Series:
    v = x.to_numpy(dtype=float)
    v = v - v.max()
    e = np.exp(v)
    return pd.Series(e / e.sum(), index=x.index)
