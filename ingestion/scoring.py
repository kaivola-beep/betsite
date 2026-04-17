"""Standalone probability scoring from an enriched starts DataFrame.

This is the V1 scorer: a simple, transparent, log-linear blend of
history-derived features and the market share. It intentionally
avoids depending on historical race-by-race training data — which we
don't yet have in bulk — and is therefore usable immediately against a
single card.

Score components (all within-race z-scored so they're comparable):

* ``form_z``     = -z(mean(prior_finishes[:N]))           # lower = better
* ``speed_z``    = -z(mean(prior_km_times[:N]))           # faster = better
* ``class_z``    =  z(log1p(earnings_per_start))
* ``quality_z``  =  z(log1p(sum(prior_earnings[:N])))
* ``gallop_z``   = -z(gallop_risk)
* ``layoff_z``   = -z(days_since_last_start)
* ``market_z``   =  z(logit(market_share))

Final per-race probability:

    logit = w·features  -> softmax within race

Weights are set in :class:`ScoringWeights`. Market is a strong prior;
we keep its weight at ~0.4 so heppa history has the chance to move the
estimate away from the crowd.

Bootstrap uncertainty is produced by adding random perturbations to
the feature weights (Dirichlet noise around the central weights) and
re-scoring ``n_boot`` times, then reporting mean / sd / 5–95 %
quantiles per horse.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Weights
# ---------------------------------------------------------------------------

@dataclass
class ScoringWeights:
    form: float = 0.22
    speed: float = 0.18
    class_: float = 0.12        # (class_rating / earnings per start)
    quality: float = 0.10
    gallop: float = 0.08
    layoff: float = 0.05
    market: float = 0.35        # strong prior, cannot drown out history

    def as_vector(self) -> np.ndarray:
        return np.array([
            self.form, self.speed, self.class_, self.quality,
            self.gallop, self.layoff, self.market,
        ], dtype=float)


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

def score_simple(starts_df: pd.DataFrame, *,
                 weights: Optional[ScoringWeights] = None,
                 n_recent: int = 6) -> pd.DataFrame:
    """Return a DataFrame with probability, fair odds and edge columns."""
    weights = weights or ScoringWeights()
    feats = _build_feature_frame(starts_df, n_recent=n_recent)
    w = weights.as_vector()

    feats["score"] = (feats[["form_z", "speed_z", "class_z", "quality_z",
                                "gallop_z", "layoff_z", "market_z"]].to_numpy()
                       @ w)
    feats["p_model"] = feats.groupby("race_id")["score"].transform(softmax_within_race)
    feats["fair_odds"] = 1.0 / feats["p_model"].clip(lower=1e-9)
    if "market_share" in feats:
        q = feats["market_share"].fillna(0.0)
        q_race = feats.groupby("race_id")["market_share"].transform("sum")
        implied = np.where(q_race > 0, q / q_race.replace(0, np.nan), np.nan)
        feats["p_market_implied"] = implied
        feats["edge"] = feats["p_model"] / np.where(np.isfinite(implied) & (implied > 0),
                                                       implied, np.nan)
        feats["log_edge"] = np.log(feats["edge"])
    return feats


def score_bootstrap(starts_df: pd.DataFrame, *,
                    weights: Optional[ScoringWeights] = None,
                    n_boot: int = 20, alpha: float = 20.0,
                    seed: int = 7, n_recent: int = 6) -> pd.DataFrame:
    """Bootstrap uncertainty: resample weights around the central vector.

    ``alpha`` controls Dirichlet concentration — higher means weights
    stay near the central vector, lower means more spread. Default 20
    is a modest spread.
    """
    rng = np.random.default_rng(seed)
    base = (weights or ScoringWeights()).as_vector()
    base = base / base.sum()

    feats = _build_feature_frame(starts_df, n_recent=n_recent)
    cols = ["form_z", "speed_z", "class_z", "quality_z",
             "gallop_z", "layoff_z", "market_z"]
    X = feats[cols].to_numpy(dtype=float)

    draws = np.zeros((n_boot, len(feats)), dtype=float)
    for i in range(n_boot):
        w = rng.dirichlet(base * alpha)
        scores = X @ w
        tmp = feats[["race_id"]].copy()
        tmp["_s"] = scores
        draws[i, :] = tmp.groupby("race_id")["_s"].transform(softmax_within_race).to_numpy()

    central = score_simple(starts_df, weights=weights, n_recent=n_recent)
    central["p_model_mean"] = draws.mean(axis=0)
    central["p_model_sd"] = draws.std(axis=0)
    central["p_model_p05"] = np.quantile(draws, 0.05, axis=0)
    central["p_model_p95"] = np.quantile(draws, 0.95, axis=0)
    # Re-normalise mean within race just to be safe
    central["p_model_mean"] = central.groupby("race_id")["p_model_mean"].transform(
        lambda s: s / s.sum())
    central["fair_odds_conservative"] = 1.0 / central["p_model_p05"].clip(lower=1e-9)
    return central


# ---------------------------------------------------------------------------
# Feature engineering (self-contained, independent of race_model)
# ---------------------------------------------------------------------------

def _build_feature_frame(starts_df: pd.DataFrame, *,
                          n_recent: int) -> pd.DataFrame:
    df = starts_df.copy()

    # Ensure list columns are lists
    for c in ("prior_finishes", "prior_km_times", "prior_earnings"):
        if c not in df:
            df[c] = [[] for _ in range(len(df))]
        df[c] = df[c].apply(lambda v: v if isinstance(v, list) else [])

    # Raw per-row features
    df["_mean_finish"] = df["prior_finishes"].apply(
        lambda v: float(np.mean(v[:n_recent])) if v else 6.0)
    df["_mean_km"] = df["prior_km_times"].apply(
        lambda v: float(np.mean(v[:n_recent])) if v else np.nan)
    df["_sum_earn"] = df["prior_earnings"].apply(
        lambda v: float(np.sum(v[:n_recent])) if v else 0.0)
    df["_log_earn"] = np.log1p(df["_sum_earn"].clip(lower=0))
    df["_class"] = pd.to_numeric(df.get("class_rating"), errors="coerce").fillna(0.0)
    df["_log_class"] = np.log1p(df["_class"].clip(lower=0))
    df["_gallop"] = pd.to_numeric(df.get("gallop_risk"), errors="coerce").fillna(0.0)
    df["_layoff"] = pd.to_numeric(df.get("days_since_last_start"),
                                     errors="coerce").fillna(df.get("days_since_last_start",
                                                                       pd.Series([0])).median() or 0.0)
    df["_market_logit"] = _market_logit(df.get("market_share"))

    # Within-race z-scores (sign-correct: higher = "better horse")
    df["form_z"] = _group_z(df, "_mean_finish", invert=True)
    df["speed_z"] = _group_z(df, "_mean_km", invert=True)
    df["class_z"] = _group_z(df, "_log_class", invert=False)
    df["quality_z"] = _group_z(df, "_log_earn", invert=False)
    df["gallop_z"] = _group_z(df, "_gallop", invert=True)
    df["layoff_z"] = _group_z(df, "_layoff", invert=True)
    df["market_z"] = _group_z(df, "_market_logit", invert=False)

    return df


def _market_logit(s: Optional[pd.Series]) -> pd.Series:
    if s is None:
        return pd.Series(np.zeros(0))
    p = pd.to_numeric(s, errors="coerce")
    p = p.fillna(p.median() or 0.01).clip(lower=1e-4, upper=1 - 1e-4)
    return np.log(p / (1 - p))


def _group_z(df: pd.DataFrame, col: str, *, invert: bool) -> pd.Series:
    def _z(s: pd.Series) -> pd.Series:
        mu, sd = s.mean(), s.std(ddof=0)
        if sd == 0 or np.isnan(sd):
            return pd.Series(np.zeros(len(s)), index=s.index)
        z = (s - mu) / sd
        return -z if invert else z

    return df.groupby("race_id")[col].transform(_z)


def softmax_within_race(s: pd.Series) -> pd.Series:
    v = s.to_numpy(dtype=float)
    v = v - np.nanmax(v)
    e = np.exp(v)
    e[np.isnan(e)] = 0.0
    total = e.sum()
    if total <= 0:
        return pd.Series(np.full(len(s), 1.0 / len(s)), index=s.index)
    return pd.Series(e / total, index=s.index)
