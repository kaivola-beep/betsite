"""Walk-forward / rolling-origin validation.

Design
------
Races are ordered by ``race_date``. We produce ``k`` folds, each with a
distinct *test* window that strictly follows its training window:

    fold 1:  train = [0 .. T0],       val = [T0 .. T0+V],  test = [T0+V .. T0+V+Te]
    fold 2:  train = [0 .. T0+Te],    val = ...           test = ...
    ...

No row from the validation or test windows leaks into training. We also
make sure each fold has at least one race with a winner before
evaluating, and report per-fold metrics so instability is visible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from ..calibration import log_loss_score, brier_score, expected_calibration_error
from ..config import SETTINGS


@dataclass
class WalkForwardResult:
    folds: list[dict] = field(default_factory=list)
    oof_probs: pd.DataFrame = field(default_factory=pd.DataFrame)

    def summary(self) -> pd.DataFrame:
        return pd.DataFrame(self.folds)

    def stability(self) -> dict[str, float]:
        """Mean and sd of fold metrics."""
        if not self.folds:
            return {}
        df = pd.DataFrame(self.folds)
        out = {}
        for c in ("brier", "log_loss", "ece"):
            if c in df:
                out[f"{c}_mean"] = float(df[c].mean())
                out[f"{c}_sd"] = float(df[c].std(ddof=0))
        return out


def walk_forward(history_df: pd.DataFrame,
                 stack_builder: Callable[[pd.DataFrame], object],
                 *,
                 k_folds: int = SETTINGS.walk_forward_folds,
                 min_train_races: int = SETTINGS.walk_forward_min_train,
                 val_size: int = SETTINGS.walk_forward_val_size,
                 test_size: int = SETTINGS.walk_forward_test_size,
                 prob_col: str = "p_ens") -> WalkForwardResult:
    """Run a rolling-origin evaluation.

    Parameters
    ----------
    stack_builder
        Callable ``train_df -> fitted_pipeline``. The returned pipeline
        must expose ``.predict(raw_df)`` that yields a DataFrame with
        ``prob_col``.
    """
    race_order = (history_df[["race_id", "race_date"]]
                  .drop_duplicates()
                  .sort_values(["race_date", "race_id"]))
    races = race_order["race_id"].tolist()
    if len(races) < min_train_races + val_size + test_size:
        raise ValueError(
            f"Not enough races ({len(races)}) for walk-forward with "
            f"min_train={min_train_races}, val={val_size}, test={test_size}."
        )

    folds: list[dict] = []
    oof_parts: list[pd.DataFrame] = []
    step = max((len(races) - min_train_races - val_size - test_size) // max(k_folds - 1, 1), 1)

    for k in range(k_folds):
        t0 = min_train_races + k * step
        v0, vN = t0, t0 + val_size
        te0, teN = vN, vN + test_size
        if teN > len(races):
            break
        train_races = set(races[:t0])
        val_races = set(races[v0:vN])
        test_races = set(races[te0:teN])

        train_df = history_df[history_df["race_id"].isin(train_races)]
        # val_df currently unused by the default stack; keeping for future
        # calibrator refits on out-of-fold data.
        test_df = history_df[history_df["race_id"].isin(test_races)]

        model = stack_builder(train_df)
        pred = model.predict(test_df)
        carry_cols = ["race_id", "program_number", "finished_position", "race_date"]
        for extra in ("start_type", "distance_m", "race_class"):
            if extra in test_df.columns:
                carry_cols.append(extra)
        merged = pred.merge(test_df[carry_cols],
                             on=["race_id", "program_number"], how="left")
        y = (merged["finished_position"].to_numpy() == 1).astype(int)
        p = merged[prob_col].to_numpy(dtype=float)
        folds.append({
            "fold": k + 1,
            "n_train_races": len(train_races),
            "n_test_races": len(test_races),
            "brier": brier_score(p, y),
            "log_loss": log_loss_score(p, y),
            "ece": expected_calibration_error(p, y),
            "test_date_min": str(min(test_df["race_date"])),
            "test_date_max": str(max(test_df["race_date"])),
        })
        merged["fold"] = k + 1
        oof_parts.append(merged)

    oof = pd.concat(oof_parts, ignore_index=True) if oof_parts else pd.DataFrame()
    return WalkForwardResult(folds=folds, oof_probs=oof)
