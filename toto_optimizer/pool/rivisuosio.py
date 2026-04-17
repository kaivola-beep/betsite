"""Combination popularity (rivisuosio) models.

Estimating the *per-combination* ticket popularity is the single hardest
problem in pari-mutuel pool optimisation. From Veikkaus you typically see
per-horse pool percentages in each leg, not the full joint distribution of
tickets. Three concrete models are offered here, ordered by sophistication:

1. :class:`IndependenceModel` – naive baseline: popularity(c) = prod_k s_k.
   Fast, interpretable, and exactly right only if bettors' leg choices are
   independent. In practice they are not: favourites get stacked and
   popular "angles" (e.g. banker horses) introduce positive correlation.

2. :class:`ChalkCorrelationModel` – the independence baseline multiplied
   by an explicit favourite-stacking factor
   ``lift(c) = (1 + alpha * f_fav(c))``
   where ``f_fav(c)`` is the fraction of legs in which ``c_k`` is one of
   the top-M favourites. ``alpha`` and ``M`` are calibrated from data.

3. :class:`LogLinearModel` – a log-linear correction of independence
   against observed rivisuosio ``r(c)``:

       log r(c) = log Π s_k + Σ_k theta_k * 1[c_k is top-M] + const

   ``theta_k`` captures leg-level chalk lift; ``const`` soaks up the
   takeout-independent normalising constant. Fit via least squares on
   a set of (combo, observed_share) pairs.

All three expose the same API: ``.popularity(combo, shares_per_leg)``.
The log-linear model additionally exposes ``.fit(observations)``.

These models do not claim to recover the true ticket distribution. They
are explicit, inspectable, and easy to calibrate - which is the point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class PopularityModel(Protocol):
    def popularity(self, combo: Sequence[int],
                   shares_per_leg: list[dict[int, float]]) -> float: ...


# ---------------------------------------------------------------------------
# 1. Independence baseline
# ---------------------------------------------------------------------------

@dataclass
class IndependenceModel:
    """popularity(c) = prod_k s_k. Baseline only."""

    def popularity(self, combo: Sequence[int],
                   shares_per_leg: list[dict[int, float]]) -> float:
        p = 1.0
        for k, n in enumerate(combo):
            p *= max(shares_per_leg[k].get(n, 0.0), 1e-12)
        return p


# ---------------------------------------------------------------------------
# 2. Chalk-correlation lift
# ---------------------------------------------------------------------------

@dataclass
class ChalkCorrelationModel:
    """Independence baseline with a chalk-stacking multiplier.

    Parameters
    ----------
    alpha
        Strength of the chalk lift (>= 0). Typical values 0.1 - 0.6 for
        Finnish Toto products based on qualitative observation.
    top_m
        How many top horses count as "chalk" per leg.
    """
    alpha: float = 0.25
    top_m: int = 3

    def popularity(self, combo: Sequence[int],
                   shares_per_leg: list[dict[int, float]]) -> float:
        base = 1.0
        fav_hits = 0.0
        for k, n in enumerate(combo):
            s = max(shares_per_leg[k].get(n, 0.0), 1e-12)
            base *= s
            top = sorted(shares_per_leg[k].values(), reverse=True)[: self.top_m]
            if s in top:
                fav_hits += 1.0
        if self.alpha <= 0 or len(combo) == 0:
            return base
        return base * (1.0 + self.alpha * fav_hits / len(combo))


# ---------------------------------------------------------------------------
# 3. Log-linear fit to observed rivisuosio
# ---------------------------------------------------------------------------

@dataclass
class LogLinearModel:
    """Fit theta_k and a constant to observed combination shares.

    Model: log r(c) = log Π s_k + Σ_k theta_k * 1[c_k in top_m] + const.

    Use this when you have a batch of observed (combo, observed_share)
    tuples for a single Toto draw, or - preferably - a few hundred across
    draws. A simple closed-form LS fit is used; if you have very few data
    points the chalk-correlation model is typically more robust.
    """
    top_m: int = 3
    theta: np.ndarray | None = None
    const: float = 0.0

    def fit(self, observations: Iterable[tuple[tuple[int, ...], float]],
            shares_per_leg: list[dict[int, float]]) -> "LogLinearModel":
        rows: list[np.ndarray] = []
        ys: list[float] = []
        K = len(shares_per_leg)
        for combo, r in observations:
            if r <= 0:
                continue
            # Feature: 1[c_k is top-M] per leg, plus baseline = log-indep.
            feat = np.zeros(K + 1)
            feat[-1] = 1.0  # intercept
            base = 1.0
            for k, n in enumerate(combo):
                s = max(shares_per_leg[k].get(n, 0.0), 1e-12)
                base *= s
                top = sorted(shares_per_leg[k].values(), reverse=True)[: self.top_m]
                if s in top:
                    feat[k] = 1.0
            rows.append(feat)
            ys.append(float(np.log(r) - np.log(base)))
        if not rows:
            self.theta = np.zeros(K)
            self.const = 0.0
            return self
        X = np.vstack(rows)
        y = np.asarray(ys, dtype=float)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        self.theta = coef[:-1]
        self.const = float(coef[-1])
        return self

    def popularity(self, combo: Sequence[int],
                   shares_per_leg: list[dict[int, float]]) -> float:
        K = len(shares_per_leg)
        if self.theta is None:
            self.theta = np.zeros(K)
        base = 1.0
        lift = self.const
        for k, n in enumerate(combo):
            s = max(shares_per_leg[k].get(n, 0.0), 1e-12)
            base *= s
            top = sorted(shares_per_leg[k].values(), reverse=True)[: self.top_m]
            if s in top:
                lift += float(self.theta[k])
        return base * float(np.exp(lift))


# ---------------------------------------------------------------------------
# Helper: wrap any PopularityModel as a "combo_popularity" callable
# ---------------------------------------------------------------------------

def as_callable(model: PopularityModel):
    """Return a function compatible with :mod:`optimizer.objective_functions`."""
    def _fn(combo, ctx):
        return model.popularity(combo, ctx.s_leg)
    return _fn
