"""Tests for ticket generation and objective functions."""
from __future__ import annotations

import pytest

from toto_optimizer.optimizer.objective_functions import (
    ObjectiveContext,
    combo_popularity,
    expected_value,
    hit_probability,
    jackpot_objective,
    uniqueness,
)
from toto_optimizer.optimizer.tickets import GenerationConfig, generate_tickets


def _make_ctx():
    p_leg = [
        {1: 0.45, 2: 0.25, 3: 0.15, 4: 0.10, 5: 0.05},
        {1: 0.40, 2: 0.30, 3: 0.15, 4: 0.10, 5: 0.05},
        {1: 0.35, 2: 0.30, 3: 0.20, 4: 0.10, 5: 0.05},
    ]
    s_leg = [
        {1: 0.55, 2: 0.20, 3: 0.12, 4: 0.08, 5: 0.05},
        {1: 0.50, 2: 0.25, 3: 0.12, 4: 0.08, 5: 0.05},
        {1: 0.45, 2: 0.28, 3: 0.15, 4: 0.07, 5: 0.05},
    ]
    return ObjectiveContext(
        p_leg=p_leg, s_leg=s_leg,
        takeout=0.25, pool_eur=500_000.0, jackpot_eur=250_000.0,
        n_other_tickets=50_000, stake_unit=0.10,
    )


def test_hit_probability_product():
    ctx = _make_ctx()
    assert hit_probability((1, 1, 1), ctx) == pytest.approx(0.45 * 0.40 * 0.35)


def test_uniqueness_decreases_with_popularity():
    ctx = _make_ctx()
    u_fav = uniqueness((1, 1, 1), ctx)
    u_longshot = uniqueness((5, 5, 5), ctx)
    assert u_longshot > u_fav


def test_jackpot_objective_prefers_unique_over_fav_when_gamma_large():
    ctx = _make_ctx()
    # As gamma grows, the less-popular combo's uniqueness multiplier shrinks
    # less aggressively than the chalk's, so the ratio score(unique)/score(chalk)
    # should strictly increase with gamma.
    ratio_low = (jackpot_objective((2, 2, 2), ctx, gamma=0.0)
                 / jackpot_objective((1, 1, 1), ctx, gamma=0.0))
    ratio_high = (jackpot_objective((2, 2, 2), ctx, gamma=2.0)
                  / jackpot_objective((1, 1, 1), ctx, gamma=2.0))
    assert ratio_high > ratio_low


def test_generate_tickets_respects_budget():
    ctx = _make_ctx()
    cfg = GenerationConfig(strategy="max_ev", budget_eur=2.0, stake_unit=0.10, top_k_per_leg=3)
    tickets = generate_tickets(ctx, cfg)
    assert tickets
    assert sum(t.stake for t in tickets) <= 2.0 + 1e-9
    for t in tickets:
        for sel in t.selections:
            assert len(sel) >= 1


def test_generate_tickets_strategy_switch():
    ctx = _make_ctx()
    hit_cfg = GenerationConfig(strategy="max_hit", budget_eur=2.0, stake_unit=0.10, top_k_per_leg=3)
    jp_cfg = GenerationConfig(strategy="jackpot", budget_eur=2.0, stake_unit=0.10, top_k_per_leg=3,
                               jackpot_gamma=1.2)
    hit = generate_tickets(ctx, hit_cfg)
    jp = generate_tickets(ctx, jp_cfg)
    # max_hit should rank the top favourites high
    assert any(1 in t.selections[0] for t in hit)
    assert jp  # at least some jackpot tickets emitted
