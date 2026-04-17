"""Typer CLI: one command that chains all the pieces together.

::

    # Show candidate cards today (just the id + venue)
    python -m ingestion.pipeline today

    # Full end-to-end prediction for a given Veikkaus card
    python -m ingestion.pipeline predict --card-id 443210972 --last-n 20 --bootstrap 20 --out predictions.csv

    # Diagnose what data is available for a card without scoring
    python -m ingestion.pipeline inspect-card --card-id 443210972

    # Manual horse-ID mapping (for cards where Veikkaus does not expose
    # hippoHorseId and name search fails):
    python -m ingestion.pipeline predict --card-id 443210972 --horse-map .\\manual_map.csv
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import track

from heppa.api import HippoApi
from heppa.client import from_env as heppa_from_env
from veikkaus.client import from_env as veikkaus_from_env
from veikkaus.toto import TotoInfo

from .enrichment import (
    EnrichmentResult,
    enrich_with_history,
    fetch_card_starts,
    load_horse_map,
    resolve_hippo_ids,
)
from .scoring import ScoringWeights, score_bootstrap, score_simple


app = typer.Typer(add_completion=False,
                   help="End-to-end Toto prediction pipeline "
                        "(Veikkaus + heppa + scoring).")
console = Console()
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_clients():
    vc = veikkaus_from_env()
    hc = heppa_from_env()
    return vc, hc


def _display_table(df: pd.DataFrame, *, title: str, columns: list[str]):
    cols = [c for c in columns if c in df.columns]
    t = Table(title=title)
    for c in cols:
        t.add_column(c)
    for _, row in df.iterrows():
        t.add_row(*[("" if pd.isna(v) else _fmt(v, c)) for c, v in zip(cols, row[cols])])
    console.print(t)


def _fmt(v, col: str) -> str:
    if isinstance(v, float):
        if col.startswith("p_") or col in ("edge", "gallop_risk"):
            return f"{v:.2%}" if col.startswith("p_") else f"{v:.3f}"
        if col in ("fair_odds", "fair_odds_conservative"):
            return f"{v:.2f}"
        return f"{v:.2f}"
    return str(v)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def today():
    """List today's Veikkaus cards."""
    vc, _ = _build_clients()
    cards = TotoInfo(vc).cards_today()
    t = Table(title=f"Cards today ({len(cards)})")
    for c in ("cardId", "trackName", "meetDate", "totoPools"):
        t.add_column(c)
    for c in cards:
        t.add_row(str(c.get("cardId") or c.get("id")),
                   str(c.get("trackName") or c.get("track") or ""),
                   str(c.get("meetDate") or c.get("date") or ""),
                   ",".join(c.get("totoPools") or []))
    console.print(t)


@app.command("inspect-card")
def inspect_card(card_id: str = typer.Option(...)):
    """Fetch the card and report how many horses have resolvable hippo IDs."""
    vc, hc = _build_clients()
    info = TotoInfo(vc)
    starts = fetch_card_starts(info, card_id)
    resolved = resolve_hippo_ids(starts)
    n_total = len(resolved)
    n_resolved = int(resolved["hippo_horse_id"].notna().sum())
    console.print(f"[bold]Card {card_id}[/bold]: {n_total} runners, "
                  f"{n_resolved} with inline hippo horseId.")
    _display_table(resolved, title="Runners",
                    columns=["race_id", "program_number", "horse_name",
                             "driver_id", "market_share", "hippo_horse_id"])
    if n_resolved < n_total:
        console.print(
            "[yellow]Missing hippo_horse_id for some runners. Options:\n"
            "  1) Build a CSV mapping ('horse_name,hippo_horse_id') and pass "
            "it via --horse-map.\n"
            "  2) Enable --name-search (best-effort; endpoint path not yet "
            "confirmed).\n[/yellow]")


@app.command()
def predict(card_id: str = typer.Option(...),
            last_n: int = typer.Option(20, "--last-n",
                                         help="Recent starts to pull per horse."),
            bootstrap: int = typer.Option(20, "--bootstrap",
                                            help="Bootstrap samples (0=off)."),
            reference_date: Optional[str] = typer.Option(None, "--ref-date"),
            horse_map: Optional[Path] = typer.Option(None, "--horse-map",
                                                      exists=True, readable=True),
            name_search: bool = typer.Option(False, "--name-search/--no-name-search"),
            max_workers: int = typer.Option(4, "--max-workers"),
            out: Optional[Path] = typer.Option(None, "--out"),
            show_every_race: bool = typer.Option(True, "--per-race/--no-per-race")):
    """End-to-end: Veikkaus card -> heppa history -> probabilities + edge."""
    vc, hc = _build_clients()
    info = TotoInfo(vc)
    api = HippoApi(client=hc)

    console.print(f"[cyan]1) Fetching Veikkaus card {card_id}[/cyan]")
    starts = fetch_card_starts(info, card_id)
    console.print(f"   {len(starts)} runners across "
                  f"{starts['race_id'].nunique()} races.")

    console.print("[cyan]2) Resolving Hippos horseIds[/cyan]")
    hmap = load_horse_map(horse_map) if horse_map else {}
    starts = resolve_hippo_ids(starts, horse_map=hmap, api=api,
                                name_search=name_search)
    n_total = len(starts)
    n_resolved = int(starts["hippo_horse_id"].notna().sum())
    console.print(f"   resolved {n_resolved}/{n_total} horses.")
    if n_resolved == 0:
        console.print(
            "[red]No horses could be mapped to Hippos. Aborting enrichment. "
            "Build a manual map with --horse-map or find a working name-search "
            "endpoint.[/red]"
        )
        raise typer.Exit(code=2)

    console.print(f"[cyan]3) Enriching with heppa history (last_n={last_n})[/cyan]")
    result: EnrichmentResult = enrich_with_history(
        starts, api, last_n=last_n, reference_date=reference_date,
        max_workers=max_workers,
    )
    console.print(f"   heppa fetched for {result.resolved} horses; "
                  f"{len(result.errors)} errors, {len(result.missing)} unmapped.")
    if result.errors:
        for e in result.errors[:5]:
            console.print(f"   [red]error:[/red] {e}")

    console.print("[cyan]4) Scoring[/cyan]")
    if bootstrap > 0:
        scored = score_bootstrap(result.df, n_boot=bootstrap)
    else:
        scored = score_simple(result.df)

    # --- Display ---
    if show_every_race:
        cols = ["program_number", "horse_name", "driver_name",
                 "p_model", "p_model_sd", "market_share", "p_market_implied",
                 "edge", "fair_odds", "fair_odds_conservative",
                 "gallop_risk", "days_since_last_start"]
        for rid, g in scored.groupby("race_id"):
            g = g.sort_values("p_model", ascending=False)
            _display_table(g, title=f"Race {rid}", columns=cols)

    # Top-edge picks across the whole card
    if "edge" in scored.columns:
        top_edge = (scored.dropna(subset=["edge"])
                     .sort_values("edge", ascending=False)
                     .head(15))
        _display_table(top_edge,
                        title="Top underpriced horses (edge = model / market)",
                        columns=["race_id", "program_number", "horse_name",
                                 "driver_name", "p_model", "p_market_implied",
                                 "edge", "fair_odds", "market_share"])

    if out:
        scored.to_csv(out, index=False)
        console.print(f"[green]Wrote full table to {out}[/green]")

    return scored


if __name__ == "__main__":
    app()
