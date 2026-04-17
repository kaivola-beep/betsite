"""Market comparison: fair odds, implied probabilities, and edge.

This module deliberately separates *prediction* (the stack) from
*market comparison*. The functions here do not change the model's
probabilities; they only layer comparison fields on top. That separation
is important: mixing the market into the model and then computing edge
against the same market is circular.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def fair_odds_table(pred_df: pd.DataFrame, *,
                    prob_col: str = "p_ens") -> pd.DataFrame:
    """Add fair-odds and a conservative-fair-odds column (if uncertainty
    is available in ``p_p05``)."""
    out = pred_df.copy()
    p = np.clip(out[prob_col].to_numpy(dtype=float), 1e-9, 1.0)
    out["fair_odds"] = 1.0 / p
    if "p_p05" in out.columns:
        p_low = np.clip(out["p_p05"].to_numpy(dtype=float), 1e-9, 1.0)
        # Conservative: price as if our lower credible bound were true
        out["fair_odds_conservative"] = 1.0 / p_low
    return out


def edge_table(pred_df: pd.DataFrame,
               market_df: pd.DataFrame | None = None,
               *,
               prob_col: str = "p_ens",
               market_share_col: str = "market_share") -> pd.DataFrame:
    """Return ``pred_df`` merged with implied market probabilities and
    per-row edge metrics.

    ``market_df`` is a DataFrame with at least ``race_id``,
    ``program_number`` and ``market_share_col``. If ``None``, the
    function tries to use those columns directly from ``pred_df``.
    """
    out = pred_df.copy()
    if market_df is not None:
        out = out.merge(
            market_df[["race_id", "program_number", market_share_col]],
            on=["race_id", "program_number"], how="left",
        )

    if market_share_col not in out.columns:
        out["p_market_implied"] = np.nan
        out["edge"] = np.nan
        out["log_edge"] = np.nan
        return out

    out["_share"] = out[market_share_col].fillna(0.0)
    total = out.groupby("race_id")["_share"].transform("sum")
    safe_total = total.replace(0.0, np.nan)
    out["p_market_implied"] = out["_share"] / safe_total
    # Fall back to uniform if no market info
    n = out.groupby("race_id")["program_number"].transform("count")
    out["p_market_implied"] = out["p_market_implied"].fillna(1.0 / n)

    p = np.clip(out[prob_col].to_numpy(dtype=float), 1e-9, 1.0)
    q = np.clip(out["p_market_implied"].to_numpy(dtype=float), 1e-9, 1.0)
    out["edge"] = p / q
    out["log_edge"] = np.log(out["edge"])
    out["market_odds"] = 1.0 / q
    return out.drop(columns=["_share"])
