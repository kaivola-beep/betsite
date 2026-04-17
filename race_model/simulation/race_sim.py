"""Lightweight per-race outcome sampler.

Given per-race probability distributions, draw winners and compute
empirical hit frequencies per horse. Use this to quickly estimate
downstream betting quantities without pulling in the full Toto pool
optimiser.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sample_race_winners(pred_df: pd.DataFrame, *,
                         n_sims: int = 2000,
                         prob_col: str = "p_ens",
                         seed: int | None = 42) -> pd.DataFrame:
    """Return a DataFrame with per-horse simulated win frequencies."""
    rng = np.random.default_rng(seed)
    out_rows: list[dict] = []
    for rid, g in pred_df.groupby("race_id", sort=False):
        g = g.sort_values("program_number")
        p = g[prob_col].to_numpy(dtype=float)
        p = p / p.sum()
        winners = rng.choice(len(g), size=n_sims, p=p)
        counts = np.bincount(winners, minlength=len(g))
        for i, (_, row) in enumerate(g.iterrows()):
            out_rows.append({
                "race_id": rid,
                "program_number": int(row["program_number"]),
                "horse_id": row.get("horse_id"),
                "p_model": float(p[i]),
                "p_simulated": float(counts[i] / n_sims),
                "n_wins_simulated": int(counts[i]),
            })
    return pd.DataFrame(out_rows)
