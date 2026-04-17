"""Pool / market model.

Important note on framing
-------------------------
This module estimates the *subjective* winning probability that the
Veikkaus betting pool assigns to each horse, from the observed pool
shares ``q_i``. Unlike a bookmaker market there is **no overround** to
remove: pari-mutuel shares already sum to 1. What may remain is
behavioural favourite-longshot bias (FLB): bettors tend to over-bet
longshots and, depending on market, slightly under-bet heavy favourites.

We therefore offer three *honest* options for debiasing shares into a
probability estimate. None of them is a ground truth; pick the one that
best matches your historical data and keep track of which you used.

* ``"none"``  – identity. ``pi_i = q_i``. The safe default when in doubt.
* ``"power"`` – ``pi_i propto q_i^alpha / Z``. ``alpha < 1`` pulls mass
  toward longshots, ``alpha > 1`` toward favourites. This is a single
  scalar that is easy to calibrate from historical data.
* ``"shin"``  – Shin (1993) insider-trading model. Strictly speaking it
  was formulated for bookmaker markets with an overround; we include it
  only because in practice it produces similar qualitative effects on
  share vectors, but the user should not treat it as "the correct" choice
  for pari-mutuel data.

For combination popularity (rivisuosio) see :mod:`pool.rivisuosio`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from ..app.config import SETTINGS
from ..data.schemas import PoolShare, RaceCard


DebiasMethod = Literal["none", "power", "shin"]


@dataclass
class MarketModel:
    """Debiases raw pool shares into subjective market probabilities.

    Parameters
    ----------
    method
        Debiasing method: ``'none'`` (identity, default), ``'power'`` (FLB
        power correction) or ``'shin'`` (insider-share model, not a
        perfect fit for pari-mutuel but available as a comparison).
    power_alpha
        Exponent used when ``method='power'``. ``alpha=1`` is a no-op.
        Values in roughly ``[0.85, 0.95]`` are typical for racing
        markets; callers are expected to calibrate this from observed
        data via :meth:`calibrate_power_alpha`.
    """

    method: DebiasMethod = "none"
    power_alpha: float = 0.9

    # ------------------------------------------------------------------
    # Single-race implied probabilities
    # ------------------------------------------------------------------
    def implied_probabilities(self, shares: np.ndarray) -> np.ndarray:
        q = np.asarray(shares, dtype=float)
        q = np.clip(q, 1e-9, 1.0)
        q = q / q.sum()
        if len(q) <= 1:
            return q
        if self.method == "none":
            return q
        if self.method == "power":
            pi = q ** self.power_alpha
            return pi / pi.sum()
        if self.method == "shin":
            try:
                z = _solve_shin_z(q)
            except ValueError:
                return q
            pi = (np.sqrt(z * z + 4 * (1 - z) * q * q) - z) / (2 * (1 - z))
            return pi / pi.sum()
        return q

    # ------------------------------------------------------------------
    # From a race card
    # ------------------------------------------------------------------
    def annotate_card(self, card: RaceCard,
                      extra_shares: Iterable[PoolShare] | None = None) -> pd.DataFrame:
        """Return a DataFrame with (race_id, program_number, pool_share, p_market)."""
        extra: dict[tuple[str, int], float] = {}
        for s in extra_shares or []:
            extra[(s.race_id, s.program_number)] = s.share

        rows: list[dict] = []
        for race in card.races:
            shares = []
            for h in race.horses:
                key = (race.race_id, h.program_number)
                if key in extra:
                    s = extra[key]
                elif h.pool_percentage is not None:
                    s = float(h.pool_percentage) / 100.0
                elif h.published_odds:
                    s = 1.0 / max(h.published_odds, 1.01)
                else:
                    s = np.nan
                shares.append(s)

            shares = np.asarray(shares, dtype=float)
            if np.all(np.isnan(shares)):
                shares = np.full(len(race.horses), 1.0 / len(race.horses))
                p_impl = shares.copy()
            else:
                nan_mask = np.isnan(shares)
                if nan_mask.any():
                    shares[nan_mask] = np.nanmin(shares[~nan_mask]) * 0.5
                shares = shares / shares.sum()
                p_impl = self.implied_probabilities(shares)

            for h, s, pi in zip(race.horses, shares, p_impl):
                rows.append({
                    "race_id": race.race_id,
                    "program_number": h.program_number,
                    "pool_share": float(s),
                    "p_market": float(pi),
                })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Power-alpha calibration
    # ------------------------------------------------------------------
    @staticmethod
    def calibrate_power_alpha(shares_per_race: list[np.ndarray],
                               winners_per_race: list[int],
                               alpha_grid: np.ndarray | None = None) -> float:
        """Grid-search the alpha that minimises log-loss on historical races.

        ``winners_per_race[r]`` is the index (within race r) of the winning
        horse. ``shares_per_race[r]`` are the raw pool shares for race r.
        """
        if alpha_grid is None:
            alpha_grid = np.linspace(0.70, 1.20, 51)
        best_alpha = 1.0
        best_ll = float("inf")
        for alpha in alpha_grid:
            ll = 0.0
            n = 0
            for q, w in zip(shares_per_race, winners_per_race):
                q = np.clip(q / q.sum(), 1e-9, 1.0)
                pi = q ** alpha
                pi = pi / pi.sum()
                ll -= np.log(pi[w])
                n += 1
            if n == 0:
                continue
            ll /= n
            if ll < best_ll:
                best_ll = ll
                best_alpha = float(alpha)
        return best_alpha

    # ------------------------------------------------------------------
    # Edge metrics
    # ------------------------------------------------------------------
    @staticmethod
    def edge_table(model_probs: pd.DataFrame, market_probs: pd.DataFrame,
                   prob_col_model: str = "prob",
                   prob_col_market: str = "p_market") -> pd.DataFrame:
        merged = model_probs.merge(market_probs, on=["race_id", "program_number"])
        m = np.clip(merged[prob_col_market].to_numpy(), 1e-9, 1.0)
        p = np.clip(merged[prob_col_model].to_numpy(), 1e-9, 1.0)
        merged["edge"] = p / m
        merged["log_edge"] = np.log(merged["edge"])
        merged["fair_odds"] = 1.0 / p
        merged["market_odds"] = 1.0 / m
        return merged


# ---------------------------------------------------------------------------
# Shin z solver (kept for comparison, not the default)
# ---------------------------------------------------------------------------

def _shin_sum(z: float, q: np.ndarray) -> float:
    return float(np.sum((np.sqrt(z * z + 4 * (1 - z) * q * q) - z) / (2 * (1 - z))))


def _solve_shin_z(q: np.ndarray) -> float:
    """Solve sum_i Shin(q_i; z) = 1 for z in (0, 1).

    Because pari-mutuel shares already sum to 1 we synthesise a small
    pseudo-overround from the share dispersion so that the solver has a
    non-trivial root. This is heuristic; use ``method='power'`` when
    calibrated historical data is available.
    """
    q = q / q.sum()
    overround = 1.0 + 0.05 * (np.max(q) - np.min(q))
    qr = q * overround
    if _shin_sum(SETTINGS.shin_tol, qr) >= 1.0:
        return SETTINGS.shin_tol
    try:
        return brentq(lambda z: _shin_sum(z, qr) - 1.0,
                      SETTINGS.shin_tol, 1 - SETTINGS.shin_tol,
                      xtol=SETTINGS.shin_tol, maxiter=SETTINGS.shin_max_iter)
    except ValueError:
        return 0.0
