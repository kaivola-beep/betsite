"""CLI: python -m heppa.cli horses|drivers|trainers ..."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .client import from_env
from .discover import inspect_page
from .statistics import HeppaStatistics

app = typer.Typer(add_completion=False,
                   help="Scrape horse/driver/trainer statistics from heppa.hippos.fi.")
console = Console()


def _run(kind: str, discipline: str, start_date: str | None, end_date: str | None,
         exclude_monte: bool, out: Path | None, limit: int):
    stats = HeppaStatistics(client=from_env())
    getter = {
        "horses": stats.top_horses,
        "drivers": stats.top_drivers,
        "trainers": stats.top_trainers,
    }[kind]
    df = getter(discipline=discipline, start_date=start_date, end_date=end_date,
                exclude_monte=exclude_monte)
    df = df.head(limit) if limit else df
    t = Table(title=f"Top {kind} ({discipline}) {start_date or ''}..{end_date or ''}")
    for c in df.columns:
        t.add_column(str(c))
    for _, row in df.iterrows():
        t.add_row(*[str(v) for v in row])
    console.print(t)
    if df.attrs.get("unmapped"):
        console.print(f"[yellow]Unmapped columns: {df.attrs['unmapped']}[/yellow]")
    if out:
        df.to_csv(out, index=False)
        console.print(f"[green]Wrote {len(df)} rows to {out}[/green]")


@app.command()
def horses(discipline: str = "warmblood",
           start_date: str = typer.Option(None, "--start"),
           end_date: str = typer.Option(None, "--end"),
           exclude_monte: bool = True,
           out: Path | None = None,
           limit: int = 50):
    _run("horses", discipline, start_date, end_date, exclude_monte, out, limit)


@app.command()
def drivers(discipline: str = "warmblood",
            start_date: str = typer.Option(None, "--start"),
            end_date: str = typer.Option(None, "--end"),
            exclude_monte: bool = True,
            out: Path | None = None,
            limit: int = 50):
    _run("drivers", discipline, start_date, end_date, exclude_monte, out, limit)


@app.command()
def trainers(discipline: str = "warmblood",
             start_date: str = typer.Option(None, "--start"),
             end_date: str = typer.Option(None, "--end"),
             exclude_monte: bool = True,
             out: Path | None = None,
             limit: int = 50):
    _run("trainers", discipline, start_date, end_date, exclude_monte, out, limit)


@app.command()
def inspect(path: str = typer.Option(
                "/mobiili/statistics/horses/top/warmblood",
                "--path",
                help="Path on heppa.hippos.fi to inspect."),
            start_date: str = typer.Option(None, "--start"),
            end_date: str = typer.Option(None, "--end"),
            exclude_monte: bool = True):
    """Diagnose the page: count tables and list URLs referenced.

    Use this when the statistics commands fail with 'No tables found' —
    the page is likely a JavaScript SPA and the real data lives at an
    XHR endpoint that this command tries to surface.
    """
    params = {}
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date
    if exclude_monte:
        params["monte"] = "x"
    inspect_page(from_env(), path, params=params)


if __name__ == "__main__":
    app()
