"""Monte Carlo simulation of Toto outcomes and player pools.

Model
-----
* Race outcome: for each leg we draw the winner from the model
  probabilities ``p_leg[k]``.
* Player pool: we simulate ``N_other`` opponent tickets. Each opponent
  ticket is an i.i.d. draw where each leg's pick is sampled from the pool
  shares ``s_leg[k]``, optionally with a chalk-correlation shift that
  moves probability mass toward the favourite when previous legs also
  picked the favourite.
* Payout: the total prize pool is ``(1 - takeout) * pool + jackpot``. It
  is split equally between all tickets that hit the full combo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from ..data.schemas import Ticket
from ..optimizer.objective_functions import ObjectiveContext


@dataclass
class SimulationConfig:
    n_sims: int = 5_000
    n_other_tickets: int | None = None   # if None, use ctx.n_other_tickets
    chalk_correlation: float = 0.0
    seed: int | None = 42


@dataclass
class SimulationResult:
    ticket_summaries: list[dict] = field(default_factory=list)
    portfolio: dict = field(default_factory=dict)
    per_sim_profit: np.ndarray = field(default_factory=lambda: np.array([]))

    def to_dict(self) -> dict:
        return {
            "tickets": self.ticket_summaries,
            "portfolio": self.portfolio,
        }


def simulate(tickets: Sequence[Ticket], ctx: ObjectiveContext,
             cfg: SimulationConfig | None = None) -> SimulationResult:
    cfg = cfg or SimulationConfig()
    if not tickets:
        return SimulationResult()

    rng = np.random.default_rng(cfg.seed)
    n_sims = cfg.n_sims
    K = ctx.leg_count()
    n_other = int(cfg.n_other_tickets if cfg.n_other_tickets is not None else ctx.n_other_tickets)

    # --- Pre-compute per-leg sampling tables ---------------------------------
    # For the true outcome:
    p_legs = [_sorted_dist(ctx.p_leg[k]) for k in range(K)]
    # For opponents:
    s_legs = [_sorted_dist(ctx.s_leg[k]) for k in range(K)]

    # --- Draw race outcomes ----------------------------------------------
    true_winners = np.empty((n_sims, K), dtype=np.int32)
    for k in range(K):
        ns, ps = p_legs[k]
        true_winners[:, k] = rng.choice(ns, size=n_sims, p=ps)

    # --- Simulate opponent tickets --------------------------------------
    # For computational efficiency we sample a random number of matching
    # opponents per combo per sim using a Binomial draw rather than every
    # ticket individually. popularity(combo) ~ prob a single opponent ticket
    # matches combo. With N_other opponents, the number matching is
    # Binomial(N_other, popularity).
    ticket_stats: list[dict] = []
    total_stake = sum(t.stake for t in tickets)
    prize_pool = (1 - ctx.takeout) * ctx.pool_eur + ctx.jackpot_eur

    per_sim_profit = np.zeros(n_sims, dtype=float)

    for t in tickets:
        sel_sets = [set(s) for s in t.selections]
        # Prob that this ticket (system) wins = sum over our combos of P_hit
        combos_in_system = _expand_system(t.selections)
        stake_per_combo = t.stake / max(len(combos_in_system), 1)

        # Count simulated wins + expected payout
        wins = np.zeros(n_sims, dtype=bool)
        opp_matches = np.zeros(n_sims, dtype=int)

        # Check which simulated outcomes our system covers
        for sim_idx in range(n_sims):
            w = tuple(true_winners[sim_idx])
            if all(w[k] in sel_sets[k] for k in range(K)):
                wins[sim_idx] = True
                # Popularity of the winning combo
                pop = 1.0
                for k in range(K):
                    pop *= s_legs[k][1][list(s_legs[k][0]).index(w[k])] \
                        if w[k] in s_legs[k][0] else 1e-9
                if cfg.chalk_correlation > 0:
                    # Lift if the winner is in top-3 of shares each leg
                    lift = 1.0
                    for k in range(K):
                        top3 = sorted(ctx.s_leg[k].values(), reverse=True)[:3]
                        if ctx.s_leg[k].get(w[k], 0.0) in top3:
                            lift *= (1.0 + cfg.chalk_correlation * 0.25)
                    pop *= lift
                # Opponent matches ~ Binomial(N_other, pop)
                opp_matches[sim_idx] = int(rng.binomial(max(n_other, 1), min(pop, 1.0)))

        # Our share of the pool (per winning combo we own)
        # A system may cover multiple combos; if our ticket hits, only one
        # combo hits at a time (there's a single winning combo per sim).
        payout = np.where(
            wins,
            prize_pool * stake_per_combo / (stake_per_combo + (opp_matches + 1e-12) * ctx.stake_unit),
            0.0,
        )
        # Note: stake_per_combo / (stake_per_combo + opp_matches*stake_unit)
        # distributes the prize pool proportionally across all matching
        # stakes (us + opponents). We use one stake unit per opponent match
        # as the canonical rivisuosio interpretation.

        profit = payout - t.stake
        per_sim_profit += profit

        ticket_stats.append({
            "stake": float(t.stake),
            "selections": [list(s) for s in t.selections],
            "hit_rate": float(wins.mean()),
            "mean_payout": float(payout.mean()),
            "mean_profit": float(profit.mean()),
            "roi": float(profit.mean() / t.stake) if t.stake > 0 else 0.0,
            "p5": float(np.quantile(profit, 0.05)),
            "p95": float(np.quantile(profit, 0.95)),
            "rationale": t.rationale,
        })

    # Portfolio-level stats
    portfolio = {
        "total_stake": float(total_stake),
        "mean_profit": float(per_sim_profit.mean()),
        "median_profit": float(np.median(per_sim_profit)),
        "std_profit": float(per_sim_profit.std()),
        "roi": float(per_sim_profit.mean() / total_stake) if total_stake > 0 else 0.0,
        "hit_rate_any": float(np.mean(per_sim_profit > -total_stake)),
        "prob_profit": float(np.mean(per_sim_profit > 0)),
        "max_drawdown": float(_max_drawdown(per_sim_profit)),
        "p5_profit": float(np.quantile(per_sim_profit, 0.05)),
        "p95_profit": float(np.quantile(per_sim_profit, 0.95)),
        "jackpot_sensitivity": float(_safe_corr(
            per_sim_profit,
            (per_sim_profit > 10 * total_stake).astype(float),
        )),
    }

    return SimulationResult(ticket_summaries=ticket_stats, portfolio=portfolio,
                            per_sim_profit=per_sim_profit)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.std() == 0 or b.std() == 0 or len(a) < 2:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _sorted_dist(d: dict[int, float]) -> tuple[np.ndarray, np.ndarray]:
    items = sorted(d.items())
    ns = np.array([n for n, _ in items], dtype=np.int32)
    ps = np.array([max(p, 0.0) for _, p in items], dtype=float)
    total = ps.sum()
    if total <= 0:
        ps = np.full_like(ps, 1.0 / len(ps))
    else:
        ps = ps / total
    return ns, ps


def _expand_system(selections: list[list[int]]) -> list[tuple[int, ...]]:
    from itertools import product
    return [tuple(c) for c in product(*[sorted(set(s)) for s in selections])]


def _max_drawdown(profits: np.ndarray) -> float:
    """Worst running drawdown if we replayed sim outcomes as a sequence."""
    if len(profits) == 0:
        return 0.0
    cum = np.cumsum(profits)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    return float(-dd.min())
