"""Pool / market model.

Two problems:

1. *Pool-implied probability.* Given Veikkaus Voittaja pool percentages
   (single-race win pool), estimate the subjective winning probability the
   market assigns to each horse. We use the Shin (1993) method, which
   corrects for the favourite-longshot bias by modelling an insider share
   ``z``. For observed pool shares q_i we solve

       sum_i ( sqrt(z^2 + 4 (1 - z) q_i^2) - z ) / (2 (1 - z)) = 1

   for z in (0, 1) and then define

       pi_i = ( sqrt(z^2 + 4 (1 - z) q_i^2) - z ) / (2 (1 - z))

   The pi_i are the Shin-implied probabilities; they sum to 1 by design.
   Compared to plain normalisation (pi_i = q_i / sum q_j) the Shin method
   systematically pulls mass away from extreme favourites and toward
   longshots, matching what we see in real pari-mutuel markets.

2. *Combination popularity.* For a Toto product that requires picking the
   winner in K legs, we estimate the bettor popularity of a specific row as

       popularity(row) = prod_k pool_share_k(row_k) * C

   where ``C`` is a correlation adjustment that can model chalk-stacking
   (favourites often co-occur on tickets). The default is C=1 and can be
   calibrated from observed rivisuosio if rivisuosio data is available.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from ..app.config import SETTINGS
from ..data.schemas import PoolShare, RaceCard


@dataclass
class MarketModel:
    shin: bool = True
    chalk_correlation: float = 0.0
    """Correlation coefficient used when estimating combination popularity.
    >0 models chalk-stacking (people bet favourites together more often
    than independence would imply)."""

    # ------------------------------------------------------------------
    # Single-race implied probabilities
    # ------------------------------------------------------------------
    def implied_probabilities(self, shares: np.ndarray) -> np.ndarray:
        """Return Shin-implied (or normalised) probabilities."""
        q = np.asarray(shares, dtype=float)
        q = np.clip(q, 1e-9, 1.0)
        q = q / q.sum()
        if not self.shin or len(q) <= 1:
            return q
        try:
            z = _solve_shin_z(q)
        except ValueError:
            return q
        pi = (np.sqrt(z * z + 4 * (1 - z) * q * q) - z) / (2 * (1 - z))
        pi = pi / pi.sum()
        return pi

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
            # Prefer explicit pool share overrides, else horse.pool_percentage
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
                # No market info for this race -> flat prior
                shares = np.full(len(race.horses), 1.0 / len(race.horses))
                p_impl = shares.copy()
            else:
                # Replace NaN with minimum positive value in the race
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
    # Combination popularity (for Toto-4/5/75/76)
    # ------------------------------------------------------------------
    def combo_popularity(self, shares_per_leg: list[dict[int, float]],
                         combo: tuple[int, ...]) -> float:
        """Estimate the fraction of tickets that match ``combo``.

        ``shares_per_leg[k][n]`` is the pool share for program number ``n``
        in leg ``k``. The combination popularity is the product of shares
        with an optional chalk-correlation inflation when the combo is
        consistently on the favourite side.
        """
        base = 1.0
        fav_indicator = 0.0
        for k, n in enumerate(combo):
            s = shares_per_leg[k].get(n, 0.0)
            base *= max(s, 1e-12)
            # favourite indicator: 1 if this horse is in the top-3 shares
            top = sorted(shares_per_leg[k].values(), reverse=True)[:3]
            if s in top:
                fav_indicator += 1.0
        if self.chalk_correlation <= 0:
            return base
        lift = 1.0 + self.chalk_correlation * fav_indicator / max(1, len(combo))
        return base * lift

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
# Shin z solver
# ---------------------------------------------------------------------------

def _shin_sum(z: float, q: np.ndarray) -> float:
    return float(np.sum((np.sqrt(z * z + 4 * (1 - z) * q * q) - z) / (2 * (1 - z))))


def _solve_shin_z(q: np.ndarray) -> float:
    """Solve sum_i Shin(q_i; z) = 1 for z in (0, 1)."""
    # The function is monotone in z on (0, 1). At z=0 the expression reduces
    # to q_i^2 / sum q_j which sums to <= 1. We want a z such that the
    # insider share perfectly accounts for the overround; since shares are
    # already normalised to sum to 1, z=0 is a trivial solution. For the
    # Shin method to be meaningful we must start from *raw* shares whose sum
    # is > 1 (i.e., the overround). We emulate this by inflating q by a
    # small favourite-longshot bias factor.
    q = q / q.sum()
    # Create a pseudo overround from variance of q (more spread = more bias)
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
