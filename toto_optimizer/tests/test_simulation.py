"""End-to-end smoke test of the simulation layer."""
from __future__ import annotations

import numpy as np

from toto_optimizer.data.schemas import Ticket
from toto_optimizer.optimizer.objective_functions import ObjectiveContext
from toto_optimizer.simulation.monte_carlo import SimulationConfig, simulate


def test_simulation_runs_and_returns_portfolio():
    ctx = ObjectiveContext(
        p_leg=[{1: 0.5, 2: 0.3, 3: 0.2}, {1: 0.4, 2: 0.4, 3: 0.2}],
        s_leg=[{1: 0.5, 2: 0.3, 3: 0.2}, {1: 0.5, 2: 0.3, 3: 0.2}],
        takeout=0.25, pool_eur=10_000.0, jackpot_eur=5_000.0,
        n_other_tickets=1_000, stake_unit=0.10,
    )
    tickets = [
        Ticket(selections=[[1, 2], [1]], stake=0.20, expected_value=0.0,
                hit_probability=0.0, uniqueness=0.0, rationale="demo"),
    ]
    res = simulate(tickets, ctx, SimulationConfig(n_sims=300, seed=7))
    assert "mean_profit" in res.portfolio
    assert len(res.ticket_summaries) == 1
    assert res.per_sim_profit.shape == (300,)
    # Sanity: hit rate not impossibly high
    assert 0.0 <= res.ticket_summaries[0]["hit_rate"] <= 1.0


def test_simulation_higher_prob_means_higher_hit_rate():
    """A ticket covering all horses in every leg should always hit."""
    ctx = ObjectiveContext(
        p_leg=[{1: 0.5, 2: 0.5}, {1: 0.5, 2: 0.5}],
        s_leg=[{1: 0.5, 2: 0.5}, {1: 0.5, 2: 0.5}],
        takeout=0.25, pool_eur=100.0, jackpot_eur=0.0,
        n_other_tickets=10, stake_unit=0.10,
    )
    t_all = Ticket(selections=[[1, 2], [1, 2]], stake=0.40,
                   expected_value=0.0, hit_probability=0.0, uniqueness=0.0, rationale="")
    res = simulate([t_all], ctx, SimulationConfig(n_sims=100, seed=0))
    assert res.ticket_summaries[0]["hit_rate"] == 1.0
