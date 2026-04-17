"""Race-level block bootstrap for uncertainty estimation.

Why race-level blocks? Rows within a race are not independent: the
winner is defined by the *relative* ordering of all runners. Bootstrapping
individual rows breaks the race structure and produces artificially narrow
uncertainty bands. We therefore resample *races with replacement* and
re-train the model on each bootstrap sample.

Usage
-----
>>> bs = BootstrapUncertainty(factory=lambda: PlackettLuceBaseline(), n=20)
>>> bs.fit(train_df)
>>> draws = bs.predict_draws(test_df)   # shape (n, len(test_df))
>>> summary = bs.summarise(draws, test_df)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..config import SETTINGS


@dataclass
class BootstrapUncertainty:
    """Generic race-level bootstrap wrapper.

    ``factory`` must return a fresh, unfitted model with ``.fit(df)``
    (returns self) and ``.predict(df)`` returning a DataFrame whose
    ``prob_col`` column holds per-race probabilities.
    """

    factory: Callable[[], Any]
    n: int = SETTINGS.bootstrap_n
    prob_col: str = "p_ens"
    seed: int = SETTINGS.bootstrap_seed
    _models: list[Any] = field(default_factory=list)
    _race_ids: np.ndarray | None = None

    # ------------------------------------------------------------------
    def fit(self, df: pd.DataFrame) -> "BootstrapUncertainty":
        rng = np.random.default_rng(self.seed)
        races = df["race_id"].unique()
        self._race_ids = np.asarray(races)

        self._models = []
        for _ in range(self.n):
            sample_ids = rng.choice(races, size=len(races), replace=True)
            # Build a race-weighted training frame. Reindexing preserves
            # the integer row positions so per-group operations work.
            parts = []
            counts: dict[str, int] = {}
            for rid in sample_ids:
                counts[rid] = counts.get(rid, 0) + 1
            for rid, k in counts.items():
                block = df[df["race_id"] == rid]
                if k == 1:
                    parts.append(block)
                else:
                    for j in range(k):
                        dup = block.copy()
                        dup["race_id"] = f"{rid}__b{j}"
                        parts.append(dup)
            boot_df = pd.concat(parts, ignore_index=True)
            model = self.factory()
            model.fit(boot_df)
            self._models.append(model)
        return self

    # ------------------------------------------------------------------
    def predict_draws(self, df: pd.DataFrame) -> np.ndarray:
        """Return a ``(n_boot, n_rows)`` matrix of bootstrap probabilities."""
        draws = np.zeros((self.n, len(df)), dtype=float)
        for i, model in enumerate(self._models):
            pred = model.predict(df)
            if self.prob_col not in pred.columns:
                raise KeyError(f"Predictor returned no '{self.prob_col}' column.")
            # Align to df by race_id+program_number to be safe
            key = ["race_id", "program_number"]
            merged = df[key].merge(pred[key + [self.prob_col]], on=key, how="left")
            draws[i, :] = merged[self.prob_col].to_numpy()
        return draws

    # ------------------------------------------------------------------
    def summarise(self, draws: np.ndarray, df: pd.DataFrame) -> pd.DataFrame:
        """Return (race_id, program_number, mean, sd, p5, p95) frame."""
        summary = df[["race_id", "program_number", "horse_id"]].copy()
        summary["p_mean"] = draws.mean(axis=0)
        summary["p_sd"] = draws.std(axis=0)
        summary["p_p05"] = np.quantile(draws, 0.05, axis=0)
        summary["p_p95"] = np.quantile(draws, 0.95, axis=0)
        # Re-normalise the mean per race so it stays a valid PMF
        summary["p_mean"] = summary.groupby("race_id")["p_mean"].transform(lambda s: s / s.sum())
        return summary
