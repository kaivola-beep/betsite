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


DATE_KEYS = ("date", "cardDate", "startDate", "firstRaceStart",
             "firstRacePostTime", "beginTime", "startTime")
RACE_CONTAINER_KEYS = ("races", "raceIds", "raceIdList",
                        "raceList", "raceCount", "numRaces")


def _first(d: dict, *keys, default=""):
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return default


def _count_races(c: dict) -> int:
    for k in RACE_CONTAINER_KEYS:
        v = c.get(k)
        if v is None:
            continue
        if isinstance(v, list):
            return len(v)
        if isinstance(v, (int, float)):
            return int(v)
        # string — sometimes a comma-joined list
        if isinstance(v, str):
            return len([x for x in v.split(",") if x.strip()])
    return 0


@app.command()
def today(raw: bool = typer.Option(False, help="Print one raw card as JSON so "
                                                  "you can inspect field names.")):
    """List today's racing cards."""
    info = TotoInfo(client=from_env())
    cards = info.cards_today()

    if raw and cards:
        import json
        console.print_json(json.dumps(cards[0], ensure_ascii=False, default=str))
        return

    t = Table(title=f"Cards today ({len(cards)})")
    for c in ("id", "venue", "date", "races"):
        t.add_column(c)
    for c in cards:
        t.add_row(
            str(_first(c, "id", "cardId", "card_id")),
            str(_first(c, "trackName", "track", "venue", "place")),
            str(_first(c, *DATE_KEYS))[:16],
            str(_count_races(c)),
        )
    console.print(t)
    if cards and not any(_first(c, *DATE_KEYS) for c in cards):
        console.print("[yellow]Date column is empty — field name may have "
                      "changed. Run with --raw to inspect the JSON.[/yellow]")


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
