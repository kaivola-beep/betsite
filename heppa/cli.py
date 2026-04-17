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


def _run_horses(discipline: str, start_date: str | None, end_date: str | None,
                 limit: int, registered: bool, out: Path | None,
                 raw: bool, path: str | None):
    api = HippoApi(client=from_env())
    if raw:
        import json
        from .api import _build_horses_params
        from .discover import fetch_json
        params = _build_horses_params(discipline, start_date, end_date,
                                        limit, registered)
        data = fetch_json(api.client, path or api.horses_path, params=params)
        console.print_json(json.dumps(data[0] if isinstance(data, list) and data else data,
                                         ensure_ascii=False, default=str))
        return
    try:
        df = api.top_horses(discipline=discipline,
                             start_date=start_date, end_date=end_date,
                             limit=limit, only_registered_in_finland=registered,
                             path=path)
    except Exception as e:
        _handle_http_error(e, "horses")
        return
    _print_and_maybe_save(df, f"Top horses ({discipline}) "
                                f"{start_date or ''}..{end_date or ''}",
                           limit, out)


def _run_people(kind: str, start_date: str, end_date: str, *,
                 track: str, limit: int, order: str,
                 horse_starts: bool, pony_starts: bool,
                 out: Path | None, raw: bool, path: str | None):
    api = HippoApi(client=from_env())
    if raw:
        import json
        from .api import _build_person_params
        from .discover import fetch_json
        template = api.driver_template if kind == "drivers" else api.trainer_template
        endpoint = path or template.format(start=start_date, end=end_date)
        params = _build_person_params(track, limit, order, horse_starts, pony_starts)
        data = fetch_json(api.client, endpoint, params=params)
        console.print_json(json.dumps(data[0] if isinstance(data, list) and data else data,
                                         ensure_ascii=False, default=str))
        return
    getter = api.top_drivers if kind == "drivers" else api.top_trainers
    try:
        df = getter(start_date=start_date, end_date=end_date,
                     track=track, limit=limit, order=order,
                     horse_starts=horse_starts, pony_starts=pony_starts,
                     path=path)
    except Exception as e:
        _handle_http_error(e, kind)
        return
    _print_and_maybe_save(df, f"Top {kind} {start_date}..{end_date}",
                           limit, out)


def _handle_http_error(e: Exception, kind: str):
    import requests
    if (isinstance(e, requests.HTTPError) and e.response is not None
            and e.response.status_code == 404):
        console.print(
            f"[red]HTTP 404 at {e.response.url}[/red]\n"
            f"[yellow]The default path is a best-guess. Open "
            f"heppa.hippos.fi in a browser, navigate to the {kind} "
            f"statistics page, open DevTools (F12) -> Network -> XHR, "
            f"reload and find the request that returns JSON. Then pass "
            f"--path '/actual/path' to this command.[/yellow]"
        )
        return
    raise e


def _print_and_maybe_save(df, title: str, limit: int, out: Path | None):
    t = Table(title=title)
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
    _run_horses(discipline, start_date, end_date, limit, registered,
                 out, raw, path)


@app.command()
def drivers(start_date: str = typer.Option(..., "--start"),
            end_date: str = typer.Option(..., "--end"),
            track: str = "ALL",
            limit: int = 30,
            order: str = typer.Option("WINS", "--order",
                                        help="WINS | PRIZE_MONEY | ..."),
            horse_starts: bool = typer.Option(True, "--horse-starts/--no-horse-starts"),
            pony_starts: bool = typer.Option(False, "--pony-starts/--no-pony-starts"),
            out: Path | None = None,
            raw: bool = typer.Option(False, "--raw"),
            path: str = typer.Option(None, "--path",
                                       help="Override the endpoint path.")):
    """Top drivers over a date range (Ajajaliiga / Ohjastajat-tilastot)."""
    _run_people("drivers", start_date, end_date,
                 track=track, limit=limit, order=order,
                 horse_starts=horse_starts, pony_starts=pony_starts,
                 out=out, raw=raw, path=path)


@app.command()
def trainers(start_date: str = typer.Option(..., "--start"),
             end_date: str = typer.Option(..., "--end"),
             track: str = "ALL",
             limit: int = 30,
             order: str = "WINS",
             horse_starts: bool = typer.Option(True, "--horse-starts/--no-horse-starts"),
             pony_starts: bool = typer.Option(False, "--pony-starts/--no-pony-starts"),
             out: Path | None = None,
             raw: bool = typer.Option(False, "--raw"),
             path: str = typer.Option(None, "--path",
                                        help="Override the endpoint path.")):
    """Top trainers over a date range (Valmentajat-tilastot)."""
    _run_people("trainers", start_date, end_date,
                 track=track, limit=limit, order=order,
                 horse_starts=horse_starts, pony_starts=pony_starts,
                 out=out, raw=raw, path=path)


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
