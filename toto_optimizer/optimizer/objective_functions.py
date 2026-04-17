"""Objective functions used by the ticket optimizer.

All objectives operate on a single *combination* (tuple of program numbers,
one per leg). Higher is better.

Definitions
-----------
Let ``p_leg[k][n]`` be the model's winning probability for horse ``n`` in
leg ``k`` (normalised within a leg), and ``s_leg[k][n]`` the pool share.
For a combo ``c = (c_0, ..., c_{K-1})``:

    P_hit(c)     = prod_k p_leg[k][c_k]
    popularity(c) = prod_k s_leg[k][c_k]
    uniqueness(c) = 1 / (1 + N_other * popularity(c))
    EV(c)        = P_hit(c) * ((1 - takeout) * pool + jackpot) /
                   max(1, N_other * popularity(c) + 1)

The jackpot objective multiplies EV by ``uniqueness^gamma`` to reward
combinations that break from the crowd, which is valuable when the
jackpot is large.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence


@dataclass
class ObjectiveContext:
    """Everything an objective needs to score a combination.

    ``popularity_fn`` lets the caller plug in any rivisuosio model from
    :mod:`pool.rivisuosio` (independence, chalk, log-linear, ...). If
    ``None``, the legacy chalk-correlation heuristic is used with
    ``chalk_correlation`` as its alpha.
    """

    # p_leg[k][program_number] -> probability
    p_leg: list[dict[int, float]]
    # s_leg[k][program_number] -> pool share (fraction)
    s_leg: list[dict[int, float]]
    takeout: float
    pool_eur: float
    jackpot_eur: float
    n_other_tickets: float
    stake_unit: float = 0.10
    chalk_correlation: float = 0.0
    popularity_fn: Optional[Callable[[Sequence[int], "ObjectiveContext"], float]] = None

    def leg_count(self) -> int:
        return len(self.p_leg)


def hit_probability(combo: Sequence[int], ctx: ObjectiveContext) -> float:
    p = 1.0
    for k, n in enumerate(combo):
        p *= max(ctx.p_leg[k].get(n, 0.0), 0.0)
    return p


def combo_popularity(combo: Sequence[int], ctx: ObjectiveContext) -> float:
    """Estimated fraction of opponent tickets that match ``combo``.

    If ``ctx.popularity_fn`` is provided it is used directly (typically
    one of the models in :mod:`pool.rivisuosio`). Otherwise we fall back
    to the legacy chalk-correlation heuristic.
    """
    if ctx.popularity_fn is not None:
        return max(float(ctx.popularity_fn(combo, ctx)), 1e-18)

    pop = 1.0
    fav_hits = 0.0
    for k, n in enumerate(combo):
        s = max(ctx.s_leg[k].get(n, 0.0), 1e-12)
        pop *= s
        top3 = sorted(ctx.s_leg[k].values(), reverse=True)[:3]
        if s in top3:
            fav_hits += 1.0
    if ctx.chalk_correlation > 0:
        pop *= 1.0 + ctx.chalk_correlation * fav_hits / max(1, len(combo))
    return pop


def uniqueness(combo: Sequence[int], ctx: ObjectiveContext) -> float:
    pop = combo_popularity(combo, ctx)
    return 1.0 / (1.0 + ctx.n_other_tickets * pop)


def expected_winners(combo: Sequence[int], ctx: ObjectiveContext) -> float:
    """Expected number of rival winning tickets if this combo wins."""
    return ctx.n_other_tickets * combo_popularity(combo, ctx)


def expected_value(combo: Sequence[int], ctx: ObjectiveContext) -> float:
    """EV of ONE stake unit on this combo in a pari-mutuel setting.

    Formula: EV = P_hit * prize / (1 + expected co-winners), where the
    prize is the non-takeout share of the pool plus any jackpot.
    """
    p = hit_probability(combo, ctx)
    if p <= 0:
        return -ctx.stake_unit
    payout_pool = (1 - ctx.takeout) * ctx.pool_eur + ctx.jackpot_eur
    expected_co = expected_winners(combo, ctx)
    share = payout_pool / (1.0 + expected_co)
    return p * share - ctx.stake_unit


def jackpot_objective(combo: Sequence[int], ctx: ObjectiveContext, gamma: float = 0.5) -> float:
    """EV-weighted uniqueness; more weight on unique combos when jackpot large.

    When jackpot dominates the pool, the optimal play is to choose combos
    where the expected share per winner is maximised. Raising uniqueness to
    ``gamma`` controls how strongly we avoid the crowd.
    """
    ev = expected_value(combo, ctx)
    if ev <= -ctx.stake_unit + 1e-12:
        # Still allow scoring of combos with slightly negative EV if they are
        # extremely unique; shift the EV into the positive domain.
        ev = max(ev, 1e-9)
    u = uniqueness(combo, ctx)
    return ev * (u ** max(gamma, 0.0))


def risk_adjusted_utility(combo: Sequence[int], ctx: ObjectiveContext,
                          kelly_fraction: float = 0.05) -> float:
    """A simplified fractional-Kelly proxy.

    True Kelly for pari-mutuel is hard (payout depends on other bettors),
    so we use E[log(1 + f * edge)] with edge = payout_ratio - 1.
    """
    p = hit_probability(combo, ctx)
    if p <= 0:
        return -math.inf
    payout_pool = (1 - ctx.takeout) * ctx.pool_eur + ctx.jackpot_eur
    expected_co = expected_winners(combo, ctx)
    payout_ratio = payout_pool / (1.0 + expected_co) / max(ctx.stake_unit, 1e-9)
    edge = payout_ratio - 1.0
    # f* ~ kelly_fraction * (p*edge - (1-p)) / edge; guard vs. div0.
    f = kelly_fraction
    win_log = math.log(max(1 + f * edge, 1e-9))
    lose_log = math.log(max(1 - f, 1e-9))
    return p * win_log + (1 - p) * lose_log
