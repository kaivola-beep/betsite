"""Bucketed calibration diagnostics.

We slice the out-of-fold probabilities by:

* race size (number of starters)
* predicted-probability bucket
* time window (month or fold)
* start type (volt / auto / ...)

This surfaces miscalibration that an overall ECE would hide, e.g. a
model that is well-calibrated on 10-horse fields but over-confident in
14-horse fields.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..calibration.metrics import metrics_by_bucket, probability_bucket


def _race_size_bucket(n: int) -> str:
    if n <= 9:
        return "small (<=9)"
    if n <= 12:
        return "medium (10-12)"
    return "large (13+)"


def bucketed_report(oof_df: pd.DataFrame, *, prob_col: str = "p_ens") -> dict[str, pd.DataFrame]:
    """Return a dict of bucket-label -> metrics DataFrame."""
    df = oof_df.copy()
    df["y"] = (df["finished_position"] == 1).astype(int)
    p = df[prob_col].to_numpy(dtype=float)
    y = df["y"].to_numpy(dtype=int)

    race_size = df.groupby("race_id")["program_number"].transform("count")
    df["bucket_race_size"] = race_size.apply(_race_size_bucket)
    df["bucket_prob"] = probability_bucket(p)
    df["bucket_time"] = pd.to_datetime(df["race_date"]).dt.strftime("%Y-%m")
    if "start_type" in df:
        df["bucket_start_type"] = df["start_type"].fillna("unknown")
    else:
        df["bucket_start_type"] = "unknown"
    if "fold" in df.columns:
        df["bucket_fold"] = df["fold"].astype(str)

    out: dict[str, pd.DataFrame] = {}
    for bucket_col in ("bucket_race_size", "bucket_prob", "bucket_time",
                       "bucket_start_type", "bucket_fold"):
        if bucket_col not in df.columns:
            continue
        out[bucket_col] = metrics_by_bucket(p, y, df[bucket_col].to_numpy())
    return out
