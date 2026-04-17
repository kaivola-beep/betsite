"""CLI: python -m heppa.cli horses|drivers|trainers ...

Uses the confirmed JSON endpoint
``/heppa2_backend/statistics/best/horses`` (and best-guess paths for
drivers/trainers, overridable via environment variables
``HIPPO_DRIVERS_PATH`` / ``HIPPO_TRAINERS_PATH``).
"""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .api import HippoApi
from .client import from_env
from .discover import inspect_page

app = typer.Typer(add_completion=False,
                   help="Fetch horse/driver/trainer statistics from heppa.hippos.fi.")
console = Console()


def _run(kind: str, discipline: str, start_date: str | None, end_date: str | None,
         limit: int, registered: bool, out: Path | None):
    api = HippoApi(client=from_env())
    getter = {
        "horses": api.top_horses,
        "drivers": api.top_drivers,
        "trainers": api.top_trainers,
    }[kind]
    df = getter(discipline=discipline, start_date=start_date, end_date=end_date,
                 limit=limit, only_registered_in_finland=registered)
    t = Table(title=f"Top {kind} ({discipline}) {start_date or ''}..{end_date or ''}")
    for c in df.columns:
        t.add_column(str(c))
    for _, row in df.head(limit or 50).iterrows():
        t.add_row(*[("" if v is None else str(v)) for v in row])
    console.print(t)
    if out:
        df.to_csv(out, index=False)
        console.print(f"[green]Wrote {len(df)} rows to {out}[/green]")


@app.command()
def horses(discipline: str = "warmblood",
           start_date: str = typer.Option(None, "--start"),
           end_date: str = typer.Option(None, "--end"),
           limit: int = 50,
           registered: bool = True,
           out: Path | None = None):
    _run("horses", discipline, start_date, end_date, limit, registered, out)


@app.command()
def drivers(discipline: str = "warmblood",
            start_date: str = typer.Option(None, "--start"),
            end_date: str = typer.Option(None, "--end"),
            limit: int = 50,
            registered: bool = True,
            out: Path | None = None):
    _run("drivers", discipline, start_date, end_date, limit, registered, out)


@app.command()
def trainers(discipline: str = "warmblood",
             start_date: str = typer.Option(None, "--start"),
             end_date: str = typer.Option(None, "--end"),
             limit: int = 50,
             registered: bool = True,
             out: Path | None = None):
    _run("trainers", discipline, start_date, end_date, limit, registered, out)


@app.command()
def inspect(path: str = typer.Option(
                "/mobiili/statistics/horses/top/warmblood",
                "--path",
                help="Path on heppa.hippos.fi to inspect (HTML page)."),
            start_date: str = typer.Option(None, "--start"),
            end_date: str = typer.Option(None, "--end")):
    """Diagnose a page: count tables and list JSON endpoint candidates.

    Mostly useful when the backend moves. The canonical horses
    endpoint is /heppa2_backend/statistics/best/horses.
    """
    params = {}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    inspect_page(from_env(), path, params=params)


if __name__ == "__main__":
    app()
