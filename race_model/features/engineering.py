"""Race-aware feature engineering.

Design principles:

* **Relative, not absolute.** For every continuous feature we produce
  both the raw value *and* its within-race z-score. The within-race
  z-score is what most models should consume because the absolute
  scale (a 76.5s km-time) means very little without context (a
  76.5s km-time in a cheap handicap is fast; in an elite stakes race
  it's slow).
* **Recency-weighted form.** Recent starts weigh more. We use
  exponential decay and cap at a configurable window.
* **Opponent-adjusted performance.** Raw finish positions are biased
  by the strength of the field a horse has been running against. We
  adjust finishes by the median strength of historical opponents.
* **Interactions.** Horse × distance, horse × start-type and
  driver × post-position interactions are added when the encoding is
  stable.
* **Missingness as signal.** For every optional column we add a
  ``<name>_missing`` flag that preserves the information that data
  was unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


FEATURE_COLS: list[str] = [
    "form_index_z",
    "speed_index_z",
    "earnings_index_z",
    "class_rating_z",
    "speed_rating_z",
    "stamina_rating_z",
    "post_penalty_z",
    "gallop_risk_z",
    "layoff_penalty_z",
    "equipment_delta",
    "shoeing_delta",
    "opp_adj_form_z",
    "distance_fit_z",
    "start_type_fit_z",
    "driver_post_interaction_z",
    "carried_weight_delta_z",
    "market_share_logit",
    "market_share_z",
    # Missingness flags — preserved as-is (0/1)
    "missing_speed_rating",
    "missing_class_rating",
    "missing_market",
]

NO_MARKET_FEATURE_COLS: list[str] = [
    c for c in FEATURE_COLS
    if c not in {"market_share_logit", "market_share_z", "missing_market"}
]


@dataclass
class FeatureConfig:
    form_decay: float = 0.6
    max_recent: int = 6
    layoff_sweet_days: int = 21
    layoff_flat_days: int = 90


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _weighted_avg(values, decay: float, max_n: int) -> float | None:
    if values is None or len(values) == 0:
        return None
    vs = list(values)[:max_n]
    w = np.array([decay ** i for i in range(len(vs))])
    w /= w.sum()
    return float(np.dot(w, np.asarray(vs, dtype=float)))


def _layoff_penalty(days, cfg: FeatureConfig) -> float:
    if days is None or pd.isna(days):
        return 0.0
    days = float(days)
    if days <= cfg.layoff_sweet_days:
        return 0.0
    return float(min((days - cfg.layoff_sweet_days) / cfg.layoff_flat_days, 1.5))


def _safe_zscore(s: pd.Series) -> pd.Series:
    mu = s.mean()
    sd = s.std(ddof=0)
    if sd == 0 or np.isnan(sd):
        return pd.Series(np.zeros(len(s), dtype=float), index=s.index)
    return (s - mu) / sd


def _groupwise_z(df: pd.DataFrame, col: str, group: str = "race_id",
                  invert_sign: bool = False) -> pd.Series:
    z = df.groupby(group)[col].transform(_safe_zscore)
    return -z if invert_sign else z


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_features(df: pd.DataFrame, *, cfg: FeatureConfig | None = None) -> pd.DataFrame:
    cfg = cfg or FeatureConfig()
    df = df.copy()

    # Ensure list columns are lists
    for c in ("prior_finishes", "prior_km_times",
              "prior_earnings", "prior_opponent_strengths"):
        if c not in df.columns:
            df[c] = [[] for _ in range(len(df))]
        df[c] = df[c].apply(lambda v: v if isinstance(v, list) else [])

    # --- Raw aggregates -------------------------------------------------
    df["form_index"] = df["prior_finishes"].apply(
        lambda v: _weighted_avg(v, cfg.form_decay, cfg.max_recent) or 6.0
    )
    df["speed_index"] = df["prior_km_times"].apply(
        lambda v: _weighted_avg(v, cfg.form_decay, cfg.max_recent)
    )
    df["earnings_index"] = df["prior_earnings"].apply(
        lambda v: float(np.log1p(_weighted_avg(v, cfg.form_decay, cfg.max_recent) or 0.0))
    )
    df["opp_mean_strength"] = df["prior_opponent_strengths"].apply(
        lambda v: _weighted_avg(v, cfg.form_decay, cfg.max_recent) or 0.0
    )
    # Opponent-adjusted finish: low finish against strong opponents is better
    df["opp_adj_form"] = df["form_index"] - 2.0 * df["opp_mean_strength"]

    df["layoff_penalty"] = df["days_since_last_start"].apply(lambda d: _layoff_penalty(d, cfg))

    # --- Post-position penalty (sign-corrected to "higher = better") ----
    df["n_runners"] = df.groupby("race_id")["program_number"].transform("count")
    df["post_penalty"] = np.where(
        df["start_type"].fillna("").str.lower() == "auto",
        0.05 * np.maximum(df["post_position"].fillna(1) - df["n_runners"] / 2, 0),
        np.maximum(df["post_position"].fillna(1) - (df["n_runners"] + 1) / 2, 0)
        / np.maximum(df["n_runners"] / 2, 1),
    )

    # --- Ratings with missingness flags ---------------------------------
    for src, flag in [("speed_rating", "missing_speed_rating"),
                       ("class_rating", "missing_class_rating")]:
        df[flag] = df[src].isna().astype(int)
    df["missing_market"] = df["market_share"].isna().astype(int) if "market_share" in df else 1
    for c in ("speed_rating", "class_rating", "stamina_rating", "gallop_risk",
              "speed_index", "carried_weight_kg"):
        if c in df:
            df[c] = df.groupby("race_id")[c].transform(lambda s: s.fillna(s.median()))
            df[c] = df[c].fillna(df[c].median()).fillna(0.0)

    # --- Interactions ---------------------------------------------------
    # Distance fit: speed rating weighted by distance category
    long_race = (df["distance_m"].fillna(2100) > 2400).astype(float)
    df["distance_fit"] = df["stamina_rating"] * long_race + df["speed_rating"] * (1 - long_race)

    # Start-type fit: auto starts reward raw speed; volt rewards class
    is_auto = (df["start_type"].fillna("").str.lower() == "auto").astype(float)
    df["start_type_fit"] = df["speed_rating"] * is_auto + df["class_rating"] * (1 - is_auto)

    # Driver × post: outer posts penalise weaker drivers more
    driver_hash = df["driver_id"].fillna("NA").map(lambda s: hash(s) % 1000 / 1000.0)
    df["driver_post_interaction"] = driver_hash * df["post_penalty"]

    # Carried-weight delta from race median
    if "carried_weight_kg" in df:
        df["carried_weight_delta"] = df["carried_weight_kg"] - df.groupby("race_id")["carried_weight_kg"].transform("median")
    else:
        df["carried_weight_delta"] = 0.0

    # Market features (only meaningful for 'with_market' pipeline)
    if "market_share" in df:
        ms = df["market_share"].fillna(1e-3).clip(1e-6, 1 - 1e-6)
        df["market_share_logit"] = np.log(ms / (1 - ms))
    else:
        df["market_share_logit"] = 0.0

    # --- Z-scoring within race (the key race-aware step) ----------------
    df["form_index_z"]           = _groupwise_z(df, "form_index", invert_sign=True)
    df["speed_index_z"]          = _groupwise_z(df, "speed_index", invert_sign=True)
    df["earnings_index_z"]       = _groupwise_z(df, "earnings_index")
    df["class_rating_z"]         = _groupwise_z(df, "class_rating")
    df["speed_rating_z"]         = _groupwise_z(df, "speed_rating")
    df["stamina_rating_z"]       = _groupwise_z(df, "stamina_rating")
    df["post_penalty_z"]         = _groupwise_z(df, "post_penalty", invert_sign=True)
    df["gallop_risk_z"]          = _groupwise_z(df, "gallop_risk", invert_sign=True)
    df["layoff_penalty_z"]       = _groupwise_z(df, "layoff_penalty", invert_sign=True)
    df["opp_adj_form_z"]         = _groupwise_z(df, "opp_adj_form", invert_sign=True)
    df["distance_fit_z"]         = _groupwise_z(df, "distance_fit")
    df["start_type_fit_z"]       = _groupwise_z(df, "start_type_fit")
    df["driver_post_interaction_z"] = _groupwise_z(df, "driver_post_interaction", invert_sign=True)
    df["carried_weight_delta_z"] = _groupwise_z(df, "carried_weight_delta", invert_sign=True)
    df["market_share_z"]         = _groupwise_z(df, "market_share_logit")

    df["equipment_delta"] = df["equipment_change"].fillna(False).astype(int)
    df["shoeing_delta"] = df["shoeing_change"].fillna(False).astype(int)

    # Fill any residual NaN features with 0 (z-score of a constant column)
    for c in FEATURE_COLS:
        if c in df:
            df[c] = df[c].fillna(0.0)
    return df
