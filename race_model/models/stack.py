"""Pipeline orchestrator: features → baseline + boosted (+ market)
→ ensemble → calibration → per-race probabilities.

Two preset builders are exposed:

* :func:`build_stack` – the no-market stack. Produces the "own view".
* :func:`build_stack_with_market` – adds market_share-derived features
  to the boosted model and a market channel to the ensemble. Lets you
  separate genuine prediction from market-anchored prediction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from ..calibration.methods import TemperatureScaler, IsotonicWithRenorm
from ..config import SETTINGS
from ..features import FEATURE_COLS, NO_MARKET_FEATURE_COLS, build_features
from .baseline import PlackettLuceBaseline
from .boosted import GradientBoostedHead
from .ensemble import LogLinearEnsemble


@dataclass
class StackPipeline:
    """A fitted pipeline exposing a single :meth:`predict` entry point."""

    feature_cols: list[str]
    use_market: bool
    baseline: PlackettLuceBaseline
    boosted: GradientBoostedHead
    ensemble: LogLinearEnsemble
    calibrator: Optional[object] = None

    # ------------------------------------------------------------------
    def predict(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """Return the per-horse PMF table with columns
        ``(race_id, program_number, horse_id, p_baseline, p_boosted, p_market?, p_ens)``.
        """
        feats = build_features(raw_df)

        pb = self.baseline.predict(feats)[["race_id", "program_number", "horse_id",
                                             "logit_baseline", "p_baseline"]]
        pg = self.boosted.predict(feats)[["race_id", "program_number",
                                             "logit_boosted", "p_boosted"]]
        out = pb.merge(pg, on=["race_id", "program_number"], how="left")

        if self.use_market:
            mkt = _market_as_probability(feats)
            out = out.merge(mkt, on=["race_id", "program_number"], how="left")

        out = self.ensemble.blend(out)

        if self.calibrator is not None:
            out = self.calibrator.transform(out, prob_col="p_ens")
        return out


# ---------------------------------------------------------------------------
# Market channel
# ---------------------------------------------------------------------------

def _market_as_probability(df: pd.DataFrame) -> pd.DataFrame:
    """Produce a per-race PMF from ``market_share`` (renormalised)."""
    out = df[["race_id", "program_number", "market_share"]].copy()
    out["market_share"] = out["market_share"].fillna(0.0)
    missing = out.groupby("race_id")["market_share"].transform("sum") == 0.0
    n = out.groupby("race_id")["program_number"].transform("count")
    out.loc[missing, "market_share"] = (1.0 / n)[missing]
    out["p_market"] = out.groupby("race_id")["market_share"].transform(lambda s: s / s.sum())
    return out[["race_id", "program_number", "p_market"]]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_stack(history_df: pd.DataFrame,
                *,
                use_market: bool = False,
                calibration: str = SETTINGS.calibration_method) -> StackPipeline:
    """Train the full stack on a long-format historical DataFrame."""
    feats = build_features(history_df)

    if use_market:
        feat_cols = list(FEATURE_COLS)
        weights = dict(SETTINGS.ensemble_weights_with_market)
    else:
        feat_cols = list(NO_MARKET_FEATURE_COLS)
        weights = dict(SETTINGS.ensemble_weights_no_market)

    baseline = PlackettLuceBaseline(feature_cols=feat_cols).fit(feats)
    boosted = GradientBoostedHead(feature_cols=feat_cols).fit(feats)
    ensemble = LogLinearEnsemble(weights=weights)

    # --- Calibration --------------------------------------------------
    # Fit calibrators on *in-sample* ensemble logits. For honest held-out
    # calibration, use evaluation.backtest.walk_forward to produce
    # out-of-fold probabilities and re-fit the calibrator on those.
    calibrator = _build_calibrator(calibration)
    if calibrator is not None:
        pred = baseline.predict(feats).merge(
            boosted.predict(feats)[["race_id", "program_number", "logit_boosted", "p_boosted"]],
            on=["race_id", "program_number"], how="left",
        )
        if use_market:
            pred = pred.merge(_market_as_probability(feats),
                               on=["race_id", "program_number"], how="left")
        blended = ensemble.blend(pred)
        y = (feats["finished_position"].to_numpy() == 1).astype(int)
        blended = blended.merge(feats[["race_id", "program_number", "finished_position"]],
                                 on=["race_id", "program_number"], how="left")
        calibrator.fit(blended, y, prob_col="p_ens")

    return StackPipeline(
        feature_cols=feat_cols,
        use_market=use_market,
        baseline=baseline,
        boosted=boosted,
        ensemble=ensemble,
        calibrator=calibrator,
    )


def build_stack_with_market(history_df: pd.DataFrame,
                             calibration: str = SETTINGS.calibration_method) -> StackPipeline:
    return build_stack(history_df, use_market=True, calibration=calibration)


def _build_calibrator(method: str):
    if method == "none":
        return None
    if method == "temperature":
        return TemperatureScaler()
    if method == "isotonic":
        return IsotonicWithRenorm()
    if method == "temperature+isotonic":
        return _Pipeline([TemperatureScaler(), IsotonicWithRenorm()])
    raise ValueError(f"Unknown calibration method: {method}")


class _Pipeline:
    """Tiny sequential calibrator pipeline."""
    def __init__(self, steps):
        self.steps = steps

    def fit(self, df, y, *, prob_col="p_ens"):
        for step in self.steps:
            step.fit(df, y, prob_col=prob_col)
            df = step.transform(df, prob_col=prob_col)
        return self

    def transform(self, df, *, prob_col="p_ens"):
        for step in self.steps:
            df = step.transform(df, prob_col=prob_col)
        return df
