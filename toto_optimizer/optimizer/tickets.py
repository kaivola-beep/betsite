"""Ticket generation for Toto products.

Three strategies are supported:

* ``max_hit``       – maximise the probability of hitting the combo for a
                      fixed budget. Equivalent to a 0/1 integer program:
                      select the highest-probability horses per leg subject
                      to a product-count budget.
* ``max_ev``        – maximise the expected value subject to a budget. We
                      rank individual combinations by EV and pick greedily
                      from the top of the list, using beam search to
                      explore near-optimal subsets.
* ``jackpot``       – maximise ``EV * uniqueness^gamma``. Uses the same
                      beam search as ``max_ev`` with a different scoring
                      function.

For large combinatorial spaces (e.g. Toto-75 with 5-6 favourites per leg)
the full Cartesian product is still only a few thousand combos, so we
enumerate when feasible and fall back to beam search otherwise.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from ..app.config import SETTINGS
from ..data.schemas import Ticket
from .objective_functions import (
    ObjectiveContext,
    combo_popularity,
    expected_value,
    hit_probability,
    jackpot_objective,
    uniqueness,
)


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

def _score_fn_for(strategy: str, gamma: float) -> Callable[[tuple[int, ...], ObjectiveContext], float]:
    if strategy == "max_hit":
        return hit_probability
    if strategy == "max_ev":
        return expected_value
    if strategy == "jackpot":
        return lambda c, ctx: jackpot_objective(c, ctx, gamma=gamma)
    raise ValueError(f"Unknown strategy: {strategy}")


# ---------------------------------------------------------------------------
# Combo enumeration / beam search
# ---------------------------------------------------------------------------

@dataclass
class GenerationConfig:
    strategy: str = "max_ev"            # 'max_hit' | 'max_ev' | 'jackpot'
    budget_eur: float = SETTINGS.default_budget
    stake_unit: float = SETTINGS.default_stake_unit
    top_k_per_leg: int = 6                # prune legs to top-N candidates
    max_full_enumerate: int = 200_000    # above this, use beam search
    beam_width: int = SETTINGS.beam_width
    jackpot_gamma: float = SETTINGS.jackpot_weight_gamma
    min_leg_prob: float = 0.02           # drop very unlikely horses
    max_tickets: int = 40
    allow_systems: bool = True            # allow "harava"-style systems
    max_per_leg_in_system: int = 4       # how many horses per leg in a system
    min_hit_probability: float = 0.0


def _candidate_horses(ctx: ObjectiveContext, cfg: GenerationConfig) -> list[list[int]]:
    """For each leg, return the top-N program numbers by model probability."""
    out: list[list[int]] = []
    for leg in ctx.p_leg:
        items = [(n, p) for n, p in leg.items() if p >= cfg.min_leg_prob]
        items.sort(key=lambda x: x[1], reverse=True)
        out.append([n for n, _ in items[: cfg.top_k_per_leg]])
    return out


def _beam_search(score_fn, ctx: ObjectiveContext, candidates: list[list[int]],
                 beam_width: int) -> list[tuple[tuple[int, ...], float]]:
    """Beam over legs, keeping top-``beam_width`` partial combos by a
    heuristic = cumulative probability. Final score is evaluated with
    ``score_fn`` on complete combos."""
    beam: list[tuple[tuple[int, ...], float]] = [((), 1.0)]
    for k, leg in enumerate(candidates):
        next_beam: list[tuple[tuple[int, ...], float]] = []
        for combo, heur in beam:
            for n in leg:
                p = ctx.p_leg[k].get(n, 0.0)
                if p <= 0:
                    continue
                next_beam.append((combo + (n,), heur * p))
        next_beam.sort(key=lambda x: x[1], reverse=True)
        beam = next_beam[:beam_width]
    # Rescore with real objective
    scored = [(c, score_fn(c, ctx)) for c, _ in beam]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _enumerate_or_beam(score_fn, ctx: ObjectiveContext, candidates: list[list[int]],
                       cfg: GenerationConfig) -> list[tuple[tuple[int, ...], float]]:
    total = 1
    for leg in candidates:
        total *= max(len(leg), 1)
    if total <= cfg.max_full_enumerate:
        combos = itertools.product(*candidates)
        scored = [(c, score_fn(c, ctx)) for c in combos]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    return _beam_search(score_fn, ctx, candidates, cfg.beam_width)


# ---------------------------------------------------------------------------
# Ticket building (packing combos into system tickets)
# ---------------------------------------------------------------------------

def _pack_into_systems(top_combos: list[tuple[tuple[int, ...], float]],
                       ctx: ObjectiveContext, cfg: GenerationConfig) -> list[Ticket]:
    """Turn a list of high-scoring singles into a few system tickets.

    Heuristic: greedily group combos that share program numbers per leg,
    expanding the system only while the marginal EV-per-stake stays
    positive and the budget is respected.
    """
    tickets: list[Ticket] = []
    budget_left = cfg.budget_eur
    covered: set[tuple[int, ...]] = set()

    for combo, score in top_combos:
        if combo in covered:
            continue
        # Start a new system around this combo
        system = [set([n]) for n in combo]
        tickets_needed = 1
        combos_in_system = {combo}

        # Attempt to extend each leg with the next-best horse if it improves total EV/uniqueness
        improved = True
        while improved and tickets_needed * ctx.stake_unit <= budget_left and cfg.allow_systems:
            improved = False
            for k in range(len(system)):
                if len(system[k]) >= cfg.max_per_leg_in_system:
                    continue
                # Candidate additions: horses not already in this leg, in prob order
                extras = sorted(
                    (n for n in ctx.p_leg[k] if n not in system[k]),
                    key=lambda n: ctx.p_leg[k][n], reverse=True,
                )
                for n in extras:
                    test = [set(s) for s in system]
                    test[k].add(n)
                    new_combos = _expand_system(test)
                    new_stake = len(new_combos) * ctx.stake_unit
                    if new_stake > budget_left + 1e-9:
                        continue
                    if len(new_combos) == len(combos_in_system):
                        continue
                    # Score: average EV across the system
                    ev_old = np.mean([expected_value(c, ctx) for c in combos_in_system])
                    ev_new = np.mean([expected_value(c, ctx) for c in new_combos])
                    if cfg.strategy == "max_hit":
                        gain = (sum(hit_probability(c, ctx) for c in new_combos)
                                - sum(hit_probability(c, ctx) for c in combos_in_system))
                        take = gain > 0 and new_stake <= budget_left
                    else:
                        take = ev_new >= ev_old and new_stake <= budget_left
                    if take:
                        system = test
                        combos_in_system = set(new_combos)
                        tickets_needed = len(new_combos)
                        improved = True
                        break
            if not improved:
                break

        stake = tickets_needed * ctx.stake_unit
        if stake > budget_left + 1e-9:
            continue
        budget_left -= stake
        covered.update(combos_in_system)
        hit = sum(hit_probability(c, ctx) for c in combos_in_system)
        ev = sum(expected_value(c, ctx) for c in combos_in_system)
        uniq = float(np.mean([uniqueness(c, ctx) for c in combos_in_system]))
        rationale = _build_rationale(system, ctx, score)

        tickets.append(Ticket(
            selections=[sorted(s) for s in system],
            stake=stake,
            expected_value=ev,
            hit_probability=min(hit, 1.0),
            uniqueness=uniq,
            rationale=rationale,
        ))
        if len(tickets) >= cfg.max_tickets:
            break
        if budget_left < ctx.stake_unit - 1e-9:
            break

    return tickets


def _expand_system(system: list[set[int]]) -> list[tuple[int, ...]]:
    return [tuple(c) for c in itertools.product(*[sorted(s) for s in system])]


def _build_rationale(system: list[set[int]], ctx: ObjectiveContext, score: float) -> str:
    bits: list[str] = []
    for k, sel in enumerate(system):
        names = ", ".join(str(n) for n in sorted(sel))
        top = max(sel, key=lambda n: ctx.p_leg[k].get(n, 0.0))
        p = ctx.p_leg[k].get(top, 0.0)
        s = ctx.s_leg[k].get(top, 0.0)
        edge = (p / s) if s > 0 else float("inf")
        bits.append(f"leg{k + 1}: {{{names}}} (top p={p:.2%}, share={s:.2%}, edge={edge:.2f})")
    return "; ".join(bits) + f"; score={score:.4g}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_tickets(ctx: ObjectiveContext, cfg: GenerationConfig | None = None) -> list[Ticket]:
    cfg = cfg or GenerationConfig()
    candidates = _candidate_horses(ctx, cfg)
    if any(len(c) == 0 for c in candidates):
        return []

    score_fn = _score_fn_for(cfg.strategy, cfg.jackpot_gamma)
    scored = _enumerate_or_beam(score_fn, ctx, candidates, cfg)

    if cfg.min_hit_probability > 0:
        scored = [s for s in scored if hit_probability(s[0], ctx) >= cfg.min_hit_probability]

    return _pack_into_systems(scored, ctx, cfg)


def summarise_tickets(tickets: Sequence[Ticket]) -> dict:
    if not tickets:
        return {"n_tickets": 0, "total_stake": 0.0,
                "total_ev": 0.0, "total_hit_prob": 0.0}
    return {
        "n_tickets": len(tickets),
        "total_stake": float(sum(t.stake for t in tickets)),
        "total_ev": float(sum(t.expected_value for t in tickets)),
        "total_hit_prob": float(1 - math.prod(1 - t.hit_probability for t in tickets)),
        "avg_uniqueness": float(np.mean([t.uniqueness for t in tickets])),
    }
