"""Tests for calibration metrics and bucketed diagnostics."""
from __future__ import annotations

import numpy as np

from toto_optimizer.models.calibration import (
    ProbabilityCalibrator,
    calibration_report,
    calibration_report_by_bucket,
    probability_buckets,
)


def test_calibration_report_keys():
    p = np.random.default_rng(0).uniform(0, 1, size=200)
    y = (np.random.default_rng(1).uniform(0, 1, size=200) < p).astype(int)
    r = calibration_report(p, y, n_bins=5)
    for k in ("brier", "log_loss", "ece", "n"):
        assert k in r


def test_calibration_by_bucket_reports_per_label():
    rng = np.random.default_rng(2)
    p = rng.uniform(0, 1, size=300)
    y = (rng.uniform(0, 1, size=300) < p).astype(int)
    buckets = np.where(p > 0.5, "hi", "lo")
    out = calibration_report_by_bucket(p, y, buckets, n_bins=3)
    assert set(out.keys()) == {"hi", "lo"}
    assert all("brier" in v for v in out.values())


def test_probability_buckets_labels_all_values():
    p = np.array([0.01, 0.03, 0.25, 0.7, 0.95])
    labels = probability_buckets(p)
    assert len(labels) == len(p)
    assert all(isinstance(x, str) for x in labels)


def test_isotonic_calibrator_identity_when_few_samples():
    calib = ProbabilityCalibrator(method="isotonic")
    # Too few samples -> no-op
    calib.fit(np.array([0.2, 0.5, 0.8]), np.array([0, 1, 1]))
    assert calib.model is None
