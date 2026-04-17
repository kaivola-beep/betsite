"""Metrics and reliability diagnostics for win-probability forecasts."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def brier_score(p: np.ndarray, y: np.ndarray) -> float:
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2))


def log_loss_score(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=int)
    if len(p) == 0:
        return float("nan")
    order = np.argsort(p)
    p_sorted, y_sorted = p[order], y[order]
    bins = np.array_split(np.arange(len(p)), n_bins)
    ece = 0.0
    for b in bins:
        if len(b) == 0:
            continue
        ece += (len(b) / len(p)) * abs(p_sorted[b].mean() - y_sorted[b].mean())
    return float(ece)


def reliability_curve(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Equal-population reliability diagram: return a DataFrame with the
    per-bin mean predicted probability, observed frequency and count."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=int)
    if len(p) == 0:
        return pd.DataFrame(columns=["p_mean", "y_mean", "n"])
    order = np.argsort(p)
    p_sorted, y_sorted = p[order], y[order]
    bins = np.array_split(np.arange(len(p)), n_bins)
    rows = []
    for i, b in enumerate(bins):
        if len(b) == 0:
            continue
        rows.append({
            "bin": i,
            "p_mean": float(p_sorted[b].mean()),
            "y_mean": float(y_sorted[b].mean()),
            "n": int(len(b)),
        })
    return pd.DataFrame(rows)


@dataclass
class Report:
    brier: float
    log_loss: float
    ece: float
    n: int


def summary_report(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> Report:
    return Report(
        brier=brier_score(p, y),
        log_loss=log_loss_score(p, y),
        ece=expected_calibration_error(p, y, n_bins),
        n=int(len(p)),
    )


def metrics_by_bucket(p: np.ndarray, y: np.ndarray, bucket: np.ndarray,
                      n_bins: int = 10) -> pd.DataFrame:
    """Slice metrics by any bucket label (string / int / category)."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=int)
    bucket = np.asarray(bucket)
    rows = []
    for b in pd.unique(bucket):
        mask = bucket == b
        n = int(mask.sum())
        if n < 5:
            rows.append({"bucket": str(b), "n": n, "brier": np.nan,
                         "log_loss": np.nan, "ece": np.nan})
            continue
        rep = summary_report(p[mask], y[mask], n_bins=n_bins)
        rows.append({"bucket": str(b), "n": rep.n, "brier": rep.brier,
                     "log_loss": rep.log_loss, "ece": rep.ece})
    return pd.DataFrame(rows)


def probability_bucket(p: np.ndarray,
                        edges: tuple[float, ...] = (0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.60, 1.01)) -> np.ndarray:
    """Label each probability with its bucket string."""
    p = np.asarray(p, dtype=float)
    labels = [f"[{edges[i]:.2f},{edges[i + 1]:.2f})" for i in range(len(edges) - 1)]
    idx = np.clip(np.digitize(p, edges) - 1, 0, len(labels) - 1)
    return np.array([labels[i] for i in idx])
