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
         limit: int, registered: bool, out: Path | None, raw: bool = False,
         path: str | None = None):
    api = HippoApi(client=from_env())

    if raw:
        import json
        from .api import _build_params
        from .discover import fetch_json
        default_path = {"horses": api.horses_path,
                          "drivers": api.drivers_path,
                          "trainers": api.trainers_path}[kind]
        params = _build_params(discipline, start_date, end_date, limit, registered)
        data = fetch_json(api.client, path or default_path, params=params)
        console.print_json(json.dumps(data[0] if isinstance(data, list) and data else data,
                                         ensure_ascii=False, default=str))
        return

    getter = {
        "horses": api.top_horses,
        "drivers": api.top_drivers,
        "trainers": api.top_trainers,
    }[kind]
    try:
        df = getter(discipline=discipline, start_date=start_date, end_date=end_date,
                     limit=limit, only_registered_in_finland=registered, path=path)
    except Exception as e:
        import requests
        if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code == 404:
            console.print(
                f"[red]HTTP 404 at {e.response.url}[/red]\n"
                f"[yellow]The default path is a best-guess. Open "
                f"heppa.hippos.fi in a browser, navigate to the {kind} "
                f"statistics page, open DevTools (F12) -> Network -> XHR, "
                f"reload and find the request that returns JSON. Then:\n"
                f"  1) Pass --path '/actual/path' to this command, or\n"
                f"  2) Set HIPPO_{kind.upper()}_PATH=/actual/path in your env.[/yellow]"
            )
            return
        raise

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
           out: Path | None = None,
           raw: bool = typer.Option(False, "--raw",
                                      help="Print one raw JSON record."),
           path: str = typer.Option(None, "--path",
                                      help="Override the endpoint path.")):
    _run("horses", discipline, start_date, end_date, limit, registered,
         out, raw=raw, path=path)


@app.command()
def drivers(discipline: str = "warmblood",
            start_date: str = typer.Option(None, "--start"),
            end_date: str = typer.Option(None, "--end"),
            limit: int = 50,
            registered: bool = True,
            out: Path | None = None,
            raw: bool = typer.Option(False, "--raw"),
            path: str = typer.Option(None, "--path")):
    _run("drivers", discipline, start_date, end_date, limit, registered,
         out, raw=raw, path=path)


@app.command()
def trainers(discipline: str = "warmblood",
             start_date: str = typer.Option(None, "--start"),
             end_date: str = typer.Option(None, "--end"),
             limit: int = 50,
             registered: bool = True,
             out: Path | None = None,
             raw: bool = typer.Option(False, "--raw"),
             path: str = typer.Option(None, "--path")):
    _run("trainers", discipline, start_date, end_date, limit, registered,
         out, raw=raw, path=path)


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
