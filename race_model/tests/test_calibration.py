"""Tests for the calibration layer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from race_model.calibration.methods import IsotonicWithRenorm, TemperatureScaler
from race_model.calibration.metrics import (
    brier_score,
    expected_calibration_error,
    log_loss_score,
    metrics_by_bucket,
    reliability_curve,
    summary_report,
)


def _synth_probs(seed: int = 0, n_races: int = 80):
    rng = np.random.default_rng(seed)
    rows, y = [], []
    for r in range(n_races):
        n = int(rng.integers(8, 13))
        strengths = rng.normal(0, 1, size=n)
        p = np.exp(strengths)
        p = p / p.sum()
        winner = rng.choice(n, p=p)
        for i in range(n):
            rows.append({"race_id": f"R{r}", "program_number": i + 1, "p_ens": float(p[i])})
            y.append(1 if i == winner else 0)
    return pd.DataFrame(rows), np.asarray(y)


def test_metrics_basic():
    p = np.array([0.8, 0.1, 0.6, 0.3])
    y = np.array([1, 0, 1, 0])
    assert 0 <= brier_score(p, y) <= 1
    assert log_loss_score(p, y) > 0
    assert 0 <= expected_calibration_error(p, y, n_bins=2) <= 1
    rep = summary_report(p, y, n_bins=2)
    assert rep.n == 4


def test_temperature_preserves_race_sum():
    df, y = _synth_probs(seed=0)
    ts = TemperatureScaler().fit(df, y)
    out = ts.transform(df)
    for _, g in out.groupby("race_id"):
        assert g["p_ens"].sum() == pytest.approx(1.0, abs=1e-9)


def test_temperature_reduces_log_loss_when_overconfident():
    """Sharpen/soften a synthetic set so T != 1 is clearly optimal."""
    df, y = _synth_probs(seed=1)
    # Artificially sharpen predictions to make them overconfident
    df["p_ens"] = (df["p_ens"] ** 2)
    df["p_ens"] = df.groupby("race_id")["p_ens"].transform(lambda s: s / s.sum())

    ll_before = log_loss_score(df["p_ens"].to_numpy(), y)
    ts = TemperatureScaler().fit(df, y)
    out = ts.transform(df)
    ll_after = log_loss_score(out["p_ens"].to_numpy(), y)
    assert ll_after <= ll_before + 1e-6
    # Temperature should move away from 1 to soften
    assert ts.T > 1.0


def test_isotonic_renormalises_within_race():
    df, y = _synth_probs(seed=2)
    iso = IsotonicWithRenorm().fit(df, y)
    out = iso.transform(df)
    for _, g in out.groupby("race_id"):
        assert g["p_ens"].sum() == pytest.approx(1.0, abs=1e-9)


def test_reliability_curve_returns_bins():
    df, y = _synth_probs(seed=3)
    rc = reliability_curve(df["p_ens"].to_numpy(), y, n_bins=5)
    assert set(rc.columns) >= {"p_mean", "y_mean", "n"}
    assert len(rc) >= 3


def test_metrics_by_bucket_splits_properly():
    df, y = _synth_probs(seed=4)
    bucket = np.where(df["p_ens"].to_numpy() > 0.2, "hi", "lo")
    out = metrics_by_bucket(df["p_ens"].to_numpy(), y, bucket)
    assert set(out["bucket"]) == {"hi", "lo"}
    assert (out["n"] > 0).all()
