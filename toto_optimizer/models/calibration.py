"""Probability calibration and scoring.

For win-probability forecasts we care about *calibration*: if the model
says "this horse wins with probability 0.3" it should win roughly 30 % of
the time across similar forecasts. The calibration layer supports both
isotonic regression (non-parametric, monotone) and Platt scaling (a
logistic fit), with isotonic being the default. A per-race re-normalisation
is applied afterwards so that the outputs stay a valid probability mass
function.

Metrics reported:

* Brier score      – mean squared error in probability space.
* Log loss         – negative log-likelihood.
* Expected calibration error (ECE) – mean |predicted - observed| across
  equally-populated probability bins.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


CalibMethod = Literal["isotonic", "platt", "none"]


@dataclass
class ProbabilityCalibrator:
    method: CalibMethod = "isotonic"
    model: object | None = None

    def fit(self, p: np.ndarray, y: np.ndarray) -> "ProbabilityCalibrator":
        p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
        y = np.asarray(y, dtype=int)
        if self.method == "none" or len(p) < 30:
            self.model = None
            return self
        if self.method == "platt":
            lr = LogisticRegression(max_iter=200)
            lr.fit(_logit(p).reshape(-1, 1), y)
            self.model = lr
        else:
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(p, y)
            self.model = iso
        return self

    def transform(self, df: pd.DataFrame, prob_col: str = "prob") -> pd.DataFrame:
        df = df.copy()
        if self.model is None:
            return _renormalise(df, prob_col)
        p = df[prob_col].to_numpy(dtype=float)
        p = np.clip(p, 1e-6, 1 - 1e-6)
        if isinstance(self.model, LogisticRegression):
            calibrated = self.model.predict_proba(_logit(p).reshape(-1, 1))[:, 1]
        else:
            calibrated = self.model.predict(p)
        df[prob_col] = calibrated
        return _renormalise(df, prob_col)


def _logit(p: np.ndarray) -> np.ndarray:
    return np.log(p / (1 - p))


def _renormalise(df: pd.DataFrame, prob_col: str) -> pd.DataFrame:
    df[prob_col] = df.groupby("race_id")[prob_col].transform(lambda s: s / s.sum())
    return df


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def brier_score(p: np.ndarray, y: np.ndarray) -> float:
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2))


def log_loss_score(p: np.ndarray, y: np.ndarray) -> float:
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=int)
    if len(p) == 0:
        return float("nan")
    # Equal-population bins
    order = np.argsort(p)
    p_sorted = p[order]
    y_sorted = y[order]
    bins = np.array_split(np.arange(len(p)), n_bins)
    ece = 0.0
    for b in bins:
        if len(b) == 0:
            continue
        ece += (len(b) / len(p)) * abs(p_sorted[b].mean() - y_sorted[b].mean())
    return float(ece)


def calibration_report(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> dict:
    return {
        "brier": brier_score(p, y),
        "log_loss": log_loss_score(p, y),
        "ece": expected_calibration_error(p, y, n_bins),
        "n": int(len(p)),
    }


def calibration_report_by_bucket(p: np.ndarray, y: np.ndarray,
                                  bucket: np.ndarray,
                                  n_bins: int = 10) -> dict[str, dict]:
    """Slice calibration metrics by an external bucket label.

    Use this to surface *where* a model is miscalibrated. Typical choices
    for ``bucket`` are:

    * race size (# runners)
    * probability bucket (e.g. 0-5%, 5-20%, 20-50%, >50%)
    * time bucket (month / season) to detect drift
    """
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=int)
    bucket = np.asarray(bucket)
    out: dict[str, dict] = {}
    for b in np.unique(bucket):
        mask = bucket == b
        if mask.sum() < 5:
            # Too few samples; report as NaN to be honest
            out[str(b)] = {"n": int(mask.sum()), "brier": float("nan"),
                           "log_loss": float("nan"), "ece": float("nan")}
            continue
        out[str(b)] = calibration_report(p[mask], y[mask], n_bins=n_bins)
    return out


def probability_buckets(p: np.ndarray,
                        edges: np.ndarray | None = None) -> np.ndarray:
    """Assign each ``p_i`` to a probability-bucket label (string)."""
    if edges is None:
        edges = np.array([0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.55, 1.01])
    idx = np.digitize(p, edges) - 1
    labels = [f"[{edges[i]:.2f},{edges[i + 1]:.2f})" for i in range(len(edges) - 1)]
    return np.array([labels[min(max(i, 0), len(labels) - 1)] for i in idx])
