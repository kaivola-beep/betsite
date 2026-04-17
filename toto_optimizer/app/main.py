"""CLI entry point for Toto Optimizer.

Example
-------
::

    python -m toto_optimizer.app.main demo --product toto75 --budget 20 --strategy jackpot
    python -m toto_optimizer.app.main run --card data/sample/sample_toto75.csv --budget 20
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from ..data.loaders import (
    generate_demo_card,
    load_pool_shares_from_csv,
    load_race_card,
    race_card_to_dataframe,
)
from ..data.schemas import RaceCard
from ..features.engineering import build_features
from ..models.ensemble import LogLinearEnsemble
from ..models.predict import PlackettLuceModel, ensure_prob_normalised
from ..optimizer.objective_functions import ObjectiveContext
from ..optimizer.tickets import GenerationConfig, generate_tickets, summarise_tickets
from ..pool.market_model import MarketModel
from ..simulation.monte_carlo import SimulationConfig, simulate

app = typer.Typer(add_completion=False, help="Toto betting optimizer CLI.")
console = Console()


def _run_pipeline(card: RaceCard, budget: float, strategy: str, seed: int,
                  jackpot_gamma: float, pool_shares_csv: str | None,
                  stake_unit: float):
    long_df = race_card_to_dataframe(card)
    feats = build_features(long_df)

    pl = PlackettLuceModel()  # uses prior (no historical data)
    model_probs = pl.predict_probabilities(feats)
    model_probs = ensure_prob_normalised(model_probs)

    market = MarketModel()
    extra = load_pool_shares_from_csv(pool_shares_csv) if pool_shares_csv else None
    market_probs = market.annotate_card(card, extra_shares=extra)

    ensemble = LogLinearEnsemble()
    blended = ensemble.blend(model_probs, market_probs)

    p_leg: list[dict[int, float]] = []
    s_leg: list[dict[int, float]] = []
    for race in card.races:
        g_model = blended[blended.race_id == race.race_id]
        p_leg.append(dict(zip(g_model.program_number, g_model.prob_ens)))
        g_market = market_probs[market_probs.race_id == race.race_id]
        s_leg.append(dict(zip(g_market.program_number, g_market.pool_share)))

    takeout = card.takeout if card.takeout is not None else 0.25
    # Estimate n_other_tickets from pool size if available; default heuristic:
    # assume average stake 0.80 EUR per opponent bettor
    n_other = max(int(card.total_pool / max(stake_unit, 0.05)), 1000) if card.total_pool > 0 else 20_000

    ctx = ObjectiveContext(
        p_leg=p_leg, s_leg=s_leg,
        takeout=takeout, pool_eur=card.total_pool,
        jackpot_eur=card.jackpot, n_other_tickets=n_other,
        stake_unit=stake_unit,
    )

    cfg = GenerationConfig(strategy=strategy, budget_eur=budget,
                            stake_unit=stake_unit, jackpot_gamma=jackpot_gamma)
    tickets = generate_tickets(ctx, cfg)

    sim = simulate(tickets, ctx, SimulationConfig(n_sims=2_000, seed=seed))

    # --- Pretty print ---------------------------------------------------
    _print_edge_table(card, blended, market_probs)
    _print_tickets(tickets)
    _print_simulation(sim)
    return tickets, sim


def _print_edge_table(card: RaceCard, blended, market_probs):
    # ``blended`` already has p_market + pool_share (from ensemble.blend merge)
    for race in card.races:
        g = blended[blended.race_id == race.race_id].sort_values("prob_ens", ascending=False)
        t = Table(title=f"Race {race.race_number} - {race.track} {race.distance_m}m")
        for col in ("program_number", "prob_ens", "p_market", "pool_share",
                    "fair_odds", "edge"):
            t.add_column(col)
        for _, r in g.iterrows():
            p = float(r["prob_ens"])
            q = float(r["p_market"]) if not pd.isna(r["p_market"]) else float("nan")
            s = float(r["pool_share"]) if not pd.isna(r["pool_share"]) else float("nan")
            edge = p / q if q == q and q > 0 else float("nan")
            t.add_row(
                str(int(r["program_number"])),
                f"{p:.3%}",
                f"{q:.3%}" if q == q else "-",
                f"{s:.3%}" if s == s else "-",
                f"{1 / p:.2f}" if p > 0 else "-",
                f"{edge:.2f}" if edge == edge else "-",
            )
        console.print(t)


def _print_tickets(tickets):
    t = Table(title="Generated tickets")
    for col in ("#", "stake", "hit_prob", "EV", "uniqueness", "selections"):
        t.add_column(col)
    for i, tk in enumerate(tickets, 1):
        sels = " | ".join("[" + ",".join(str(x) for x in s) + "]" for s in tk.selections)
        t.add_row(str(i), f"{tk.stake:.2f}", f"{tk.hit_probability:.2%}",
                  f"{tk.expected_value:+.2f}", f"{tk.uniqueness:.3f}", sels)
    console.print(t)


def _print_simulation(sim):
    p = sim.portfolio
    if not p:
        console.print("[yellow]No tickets simulated.[/yellow]")
        return
    t = Table(title="Monte Carlo simulation (portfolio)")
    t.add_column("metric")
    t.add_column("value")
    for k, v in p.items():
        t.add_row(k, f"{v:+.4f}" if isinstance(v, float) else str(v))
    console.print(t)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@app.command()
def demo(product: str = "toto75", races: int = 7, budget: float = 20.0,
         strategy: str = typer.Option("jackpot", help="max_hit | max_ev | jackpot"),
         jackpot: float = 250_000.0, pool: float = 500_000.0,
         gamma: float = 0.5, seed: int = 42, stake_unit: float = 0.10):
    """Run the end-to-end pipeline on randomly generated demo data."""
    card = generate_demo_card(product=product, n_races=races,
                              jackpot=jackpot, total_pool=pool, seed=seed)
    _run_pipeline(card, budget=budget, strategy=strategy, seed=seed,
                  jackpot_gamma=gamma, pool_shares_csv=None,
                  stake_unit=stake_unit)


@app.command()
def run(card: Path = typer.Option(..., exists=True),
        pool_shares: Path | None = typer.Option(None, exists=True),
        product: str = "toto75", jackpot: float = 0.0, pool_eur: float = 0.0,
        takeout: float = 0.25, budget: float = 20.0,
        strategy: str = "jackpot", gamma: float = 0.5, seed: int = 42,
        stake_unit: float = 0.10, out_json: Path | None = None):
    """Run the pipeline on a user-supplied race card file."""
    rc = load_race_card(card, product=product, jackpot=jackpot,
                        total_pool=pool_eur, takeout=takeout)
    tickets, sim = _run_pipeline(rc, budget=budget, strategy=strategy,
                                   seed=seed, jackpot_gamma=gamma,
                                   pool_shares_csv=str(pool_shares) if pool_shares else None,
                                   stake_unit=stake_unit)
    if out_json:
        out_json.write_text(json.dumps({
            "tickets": [t.model_dump() for t in tickets],
            "simulation": sim.to_dict(),
        }, indent=2, default=str), encoding="utf-8")
        console.print(f"[green]Wrote results to {out_json}[/green]")


if __name__ == "__main__":
    app()
