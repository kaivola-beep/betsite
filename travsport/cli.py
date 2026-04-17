"""CLI for travsport.

::

    python -m travsport.cli race-stats 2026-04-17_18_1
    python -m travsport.cli race-stats 2026-04-17_18_1 --raw
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from .api import RACE_STATS_TEMPLATE, TravsportApi
from .client import from_env

app = typer.Typer(add_completion=False,
                   help="Read-only Svensk Travsport JSON adapter.")
console = Console()


@app.command("race-stats")
def race_stats_cmd(race_id: str = typer.Argument(..., help="{date}_{track}_{race}"),
                    raw: bool = typer.Option(False, "--raw"),
                    out: Path | None = None,
                    last_n: int = typer.Option(6, "--last-n")):
    """Fetch parsed race stats (past performances + yearly summaries)."""
    import json
    client = from_env()
    api = TravsportApi(client=client)

    if raw:
        data = client.get_json(RACE_STATS_TEMPLATE.format(race_id=race_id))
        console.print_json(json.dumps(data, ensure_ascii=False, default=str))
        return

    stats = api.race_stats(race_id)

    t = Table(title=f"Past performances ({race_id})")
    for c in ("program_number", "prev_date", "prev_track_code",
               "prev_distance_m", "placing", "km_time_s", "win_odds",
               "prev_driver", "prev_race_type"):
        t.add_column(c)
    for _, row in stats.past_performances.head(100).iterrows():
        t.add_row(
            str(row["program_number"]),
            str(row["prev_date"])[:10] if pd.notna(row["prev_date"]) else "",
            str(row["prev_track_code"] or ""),
            str(row["prev_distance_m"] or ""),
            "" if pd.isna(row["placing"]) else str(int(row["placing"])),
            f"{row['km_time_s']:.1f}" if pd.notna(row["km_time_s"]) else "",
            f"{row['win_odds']:.2f}" if pd.notna(row["win_odds"]) else "",
            str(row["prev_driver"] or "")[:24],
            str(row["prev_race_type"] or ""),
        )
    console.print(t)

    s = Table(title=f"Horse summary ({race_id})")
    for c in ("program_number", "life_starts", "life_wins",
               "life_earnings_sek", "last_year", "last_year_starts",
               "last_year_wins", "last_year_earnings_sek"):
        s.add_column(c)
    for _, row in stats.horse_summary.iterrows():
        s.add_row(*[("" if pd.isna(v) else str(v)) for v in row[
            ["program_number", "life_starts", "life_wins",
             "life_earnings_sek", "last_year", "last_year_starts",
             "last_year_wins", "last_year_earnings_sek"]]])
    console.print(s)

    feats = stats.to_race_model_features(last_n=last_n)
    console.print("[bold cyan]race_model feature frame (preview):[/bold cyan]")
    console.print(feats.to_string(index=False))
    if out:
        stats.past_performances.to_csv(out, index=False)
        console.print(f"[green]Wrote past performances to {out}[/green]")


if __name__ == "__main__":
    app()
