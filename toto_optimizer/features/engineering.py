"""Feature engineering for Toto races.

The goal here is *not* to dump every imaginable feature into the model but
to produce a small set of interpretable, numerically well-behaved features
that a Plackett-Luce / multinomial-logit model can consume.

The following features are built per horse (within a race so that relative
comparisons stay meaningful):

* ``form_index``     – time-weighted average finishing position.
* ``speed_index``    – normalised km-time of recent starts (lower = faster).
* ``earnings_index`` – time-weighted recent earnings (log1p).
* ``class_rating``   – supplied class rating, falling back to median.
* ``speed_rating``   – supplied speed rating, falling back to median.
* ``stamina_rating`` – supplied stamina rating, fallback median.
* ``post_penalty``   – soft penalty for outer post positions on volt starts.
* ``gallop_risk``    – 0-1 probability of breaking stride (if supplied).
* ``layoff_penalty`` – long layoff penalty.
* ``equipment_delta``/``shoeing_delta`` – change indicator features.

All per-race features are z-scored within a race before model fitting so
that the coefficients are comparable across races of different quality.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


FEATURE_COLS: list[str] = [
    "form_index",
    "speed_index",
    "earnings_index",
    "class_rating_f",
    "speed_rating_f",
    "stamina_rating_f",
    "post_penalty",
    "gallop_risk_f",
    "layoff_penalty",
    "equipment_delta",
    "shoeing_delta",
]


@dataclass
class FeatureConfig:
    form_decay: float = 0.6     # geometric weight for older starts
    speed_decay: float = 0.6
    max_recent: int = 5          # consider at most N recent starts
    layoff_sweet: int = 21       # "fresh" window in days
    layoff_max_penalty_days: int = 120


def _weighted_mean(values: list[float], decay: float, max_n: int) -> float | None:
    if not values:
        return None
    vs = list(values)[:max_n]
    weights = np.array([decay ** i for i in range(len(vs))])
    weights /= weights.sum()
    return float(np.dot(weights, np.asarray(vs, dtype=float)))


def _form_index(fins: list[int], cfg: FeatureConfig) -> float:
    """Lower is better. Fallback = midfield (6.0)."""
    v = _weighted_mean([float(x) for x in fins], cfg.form_decay, cfg.max_recent)
    return 6.0 if v is None else v


def _speed_index(times: list[float], cfg: FeatureConfig) -> float | None:
    return _weighted_mean(times, cfg.speed_decay, cfg.max_recent)


def _earnings_index(earn: list[float], cfg: FeatureConfig) -> float:
    v = _weighted_mean([float(e) for e in earn], cfg.form_decay, cfg.max_recent)
    return float(np.log1p(0.0 if v is None else max(v, 0.0)))


def _layoff_penalty(days: int | None, cfg: FeatureConfig) -> float:
    """0 around the sweet window, grows linearly outside it."""
    if days is None:
        return 0.0
    if days <= cfg.layoff_sweet:
        # Slightly negative if too fresh? Keep 0.
        return 0.0
    ratio = min((days - cfg.layoff_sweet) / (cfg.layoff_max_penalty_days - cfg.layoff_sweet), 1.5)
    return float(ratio)


def _post_penalty(post: int | None, start_type: str | None, n_horses: int) -> float:
    """Outer posts on volt starts are penalised (roughly 0.0-0.6)."""
    if post is None:
        return 0.0
    st = (start_type or "").lower()
    if st == "auto" or st == "flying":
        # Auto starts are far less position-sensitive.
        return 0.1 * max(0, post - n_horses / 2) / max(1, n_horses)
    # Volt / other: penalty grows with outer lane
    mid = (n_horses + 1) / 2
    return max(0.0, (post - mid) / mid)


def _zscore(s: pd.Series) -> pd.Series:
    mu, sd = s.mean(), s.std(ddof=0)
    if sd == 0 or np.isnan(sd):
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - mu) / sd


def _groupwise_zscore(df: pd.DataFrame, cols: Iterable[str], group: str) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        # Inverse sign for features where "lower is better"
        inverse = c in {"form_index", "speed_index", "post_penalty",
                         "gallop_risk_f", "layoff_penalty"}
        z = df.groupby(group)[c].transform(_zscore)
        out[c] = -z if inverse else z
    return out


def build_features(df: pd.DataFrame, *, cfg: FeatureConfig | None = None,
                    fillna_strategy: str = "race_median") -> pd.DataFrame:
    """Build feature DataFrame from a long-format race-card DataFrame.

    Parameters
    ----------
    df : DataFrame
        Output of :func:`data.loaders.race_card_to_dataframe`.
    fillna_strategy : {"race_median", "global_median", "zero"}
        How to handle missing rating columns.
    """
    cfg = cfg or FeatureConfig()
    df = df.copy()

    # Ensure list columns are lists (CSV often leaves them as strings)
    for col in ("recent_finishes", "recent_kilometer_times", "recent_earnings"):
        df[col] = df[col].apply(lambda v: v if isinstance(v, list) else [])

    df["form_index"] = df["recent_finishes"].apply(lambda v: _form_index(v, cfg))
    df["speed_index"] = df["recent_kilometer_times"].apply(lambda v: _speed_index(v, cfg))
    df["earnings_index"] = df["recent_earnings"].apply(lambda v: _earnings_index(v, cfg))
    df["layoff_penalty"] = df["days_since_last_start"].apply(lambda d: _layoff_penalty(d, cfg))

    # Group-level n_horses for post penalty
    n_map = df.groupby("race_id")["program_number"].transform("count")
    df["post_penalty"] = [
        _post_penalty(p, s, n)
        for p, s, n in zip(df["post_position"], df["start_type"], n_map)
    ]

    # Copy rating columns (they may be None) and impute within race
    for src, dst in [("class_rating", "class_rating_f"),
                     ("speed_rating", "speed_rating_f"),
                     ("stamina_rating", "stamina_rating_f"),
                     ("gallop_risk", "gallop_risk_f")]:
        df[dst] = df[src]

    # Impute missing values
    impute_cols = ["speed_index", "class_rating_f", "speed_rating_f",
                   "stamina_rating_f", "gallop_risk_f"]
    for c in impute_cols:
        if fillna_strategy == "global_median":
            df[c] = df[c].fillna(df[c].median())
        elif fillna_strategy == "zero":
            df[c] = df[c].fillna(0.0)
        else:  # race_median
            df[c] = df.groupby("race_id")[c].transform(lambda s: s.fillna(s.median()))
            df[c] = df[c].fillna(df[c].median()).fillna(0.0)

    # Boolean -> 0/1
    df["equipment_delta"] = df["equipment_change"].fillna(False).astype(int)
    df["shoeing_delta"] = df["shoeing_change"].fillna(False).astype(int)

    # Z-score within race
    df = _groupwise_zscore(df, FEATURE_COLS, group="race_id")
    return df
