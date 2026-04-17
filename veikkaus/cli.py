"""Command-line entry for fetching live Veikkaus Toto data.

Examples
--------
::

    # List today's cards (venue + card id)
    python -m veikkaus.cli today

    # Dump a card as a race_model CSV (ready for race_model predict)
    python -m veikkaus.cli export --card-id 12345 --format race_model \\
        --out .\\today.csv

    # Dump a card as a toto_optimizer CSV + pool shares CSV
    python -m veikkaus.cli export --card-id 12345 --format toto_optimizer \\
        --out .\\card.csv --shares-out .\\shares.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from .adapters import to_race_model_starts, to_toto_optimizer_card
from .client import VeikkausClient, from_env
from .toto import TotoInfo

app = typer.Typer(add_completion=False,
                   help="Fetch read-only Toto info from Veikkaus.")
console = Console()


@app.command()
def today():
    """List today's racing cards."""
    info = TotoInfo(client=from_env())
    cards = info.cards_today()
    t = Table(title="Cards today")
    cols = ("id", "venue", "date", "races")
    for c in cols:
        t.add_column(c)
    for c in cards:
        t.add_row(
            str(c.get("id") or c.get("cardId") or ""),
            str(c.get("trackName") or c.get("track") or c.get("venue") or ""),
            str(c.get("date") or c.get("cardDate") or ""),
            str(c.get("raceCount") or len(c.get("races") or [])),
        )
    console.print(t)


@app.command()
def pools(card_id: str = typer.Option(...)):
    """List the pools (T75, T76, Voittaja, ...) of a card."""
    info = TotoInfo(client=from_env())
    pools = info.card_pools(card_id)
    t = Table(title=f"Pools in card {card_id}")
    for c in ("id", "poolType", "raceIds", "currentPool", "jackpot"):
        t.add_column(c)
    for p in pools:
        t.add_row(
            str(p.get("id") or p.get("poolId")),
            str(p.get("poolType") or p.get("type")),
            str(p.get("raceIds") or p.get("races")),
            str(p.get("currentPool") or p.get("expectedPool") or ""),
            str(p.get("jackpot") or p.get("carryOver") or ""),
        )
    console.print(t)


@app.command()
def export(card_id: str = typer.Option(...),
           fmt: str = typer.Option("race_model", "--format",
                                     help="race_model | toto_optimizer"),
           out: Path = typer.Option(...),
           shares_out: Path | None = None,
           product: str = "toto75"):
    """Download and convert a full card into a CSV ready for a downstream pipeline."""
    info = TotoInfo(client=from_env())

    if fmt == "race_model":
        df = to_race_model_starts(info, card_id)
        # Encode list columns as pipe-joined strings for round-trip with
        # race_model.data.loaders.load_starts_from_csv
        for c in ("prior_finishes", "prior_km_times",
                  "prior_earnings", "prior_opponent_strengths"):
            df[c] = df[c].apply(lambda v: "|".join(str(x) for x in (v or [])))
        df.to_csv(out, index=False)
        console.print(f"[green]Wrote {len(df)} starts to {out}[/green]")
    elif fmt == "toto_optimizer":
        card, shares = to_toto_optimizer_card(info, card_id, product=product)
        # Expand the RaceCard into the long-format CSV used by
        # toto_optimizer.data.loaders.load_race_card_from_csv
        rows = []
        for race in card.races:
            for h in race.horses:
                rows.append({
                    "race_id": race.race_id,
                    "race_number": race.race_number,
                    "track": race.track,
                    "distance_m": race.distance_m,
                    "start_type": race.start_type.value,
                    "race_class": race.race_class or "",
                    "program_number": h.program_number,
                    "name": h.name,
                    "driver": h.driver or "",
                    "trainer": h.trainer or "",
                    "post_position": h.post_position,
                    "speed_rating": h.speed_rating or "",
                    "class_rating": h.class_rating or "",
                    "stamina_rating": h.stamina_rating or "",
                    "gallop_risk": "",
                    "days_since_last_start": "",
                    "equipment_change": "",
                    "shoeing_change": "",
                    "pool_percentage": h.pool_percentage or "",
                    "published_odds": h.published_odds or "",
                    "recent_finishes": "",
                    "recent_kilometer_times": "",
                    "recent_earnings": "",
                })
        pd.DataFrame(rows).to_csv(out, index=False)
        console.print(f"[green]Wrote card CSV to {out}[/green]")

        if shares_out and shares:
            pd.DataFrame([{
                "race_id": s.race_id,
                "program_number": s.program_number,
                "share": s.share,
            } for s in shares]).to_csv(shares_out, index=False)
            console.print(f"[green]Wrote {len(shares)} pool shares to "
                          f"{shares_out}[/green]")
        console.print(f"[cyan]Card product={card.product} "
                      f"total_pool={card.total_pool} jackpot={card.jackpot}[/cyan]")
    else:
        raise typer.BadParameter(f"Unknown format: {fmt}")


if __name__ == "__main__":
    app()
