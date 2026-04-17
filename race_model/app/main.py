"""Typer CLI for training, predicting and evaluating.

Examples
--------
::

    # Generate a synthetic history and save it
    python -m race_model.app.main gen-history --out /tmp/hist.csv

    # End-to-end training + walk-forward eval
    python -m race_model.app.main evaluate --history /tmp/hist.csv

    # Predict a fresh race card (must carry the same schema as history
    # but may lack finished_position)
    python -m race_model.app.main predict --history /tmp/hist.csv --card /tmp/card.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from ..calibration.metrics import summary_report
from ..data.loaders import generate_history, load_starts_from_csv, save_history_csv
from ..evaluation.backtest import walk_forward
from ..evaluation.diagnostics import bucketed_report
from ..market.compare import edge_table, fair_odds_table
from ..models.baseline import PlackettLuceBaseline
from ..models.stack import build_stack, build_stack_with_market
from ..models.uncertainty import BootstrapUncertainty

app = typer.Typer(add_completion=False, help="Race-aware probabilistic model CLI.")
console = Console()


@app.command("gen-history")
def gen_history(out: Path = typer.Option(...), n_races: int = 300,
                n_horses: int = 120, seed: int = 42):
    """Generate and save a synthetic training history."""
    df = generate_history(n_races=n_races, n_horses=n_horses, seed=seed)
    save_history_csv(df, out)
    console.print(f"[green]Wrote {len(df)} starts across {df['race_id'].nunique()} races "
                  f"to {out}[/green]")


@app.command()
def evaluate(history: Path = typer.Option(..., exists=True),
             use_market: bool = False,
             k_folds: int = 5):
    """Walk-forward evaluation with bucketed calibration diagnostics."""
    df = load_starts_from_csv(history)

    def builder(train_df: pd.DataFrame):
        return (build_stack_with_market(train_df)
                if use_market else build_stack(train_df))

    res = walk_forward(df, builder, k_folds=k_folds)
    _print_folds(res.summary())
    console.print("[bold]Stability[/bold]:", res.stability())

    buckets = bucketed_report(res.oof_probs)
    for label, t in buckets.items():
        _print_bucket(label, t)

    p = res.oof_probs["p_ens"].to_numpy()
    y = (res.oof_probs["finished_position"] == 1).astype(int).to_numpy()
    rep = summary_report(p, y)
    console.print(
        f"[bold]OOF overall[/bold]  brier={rep.brier:.4f}  "
        f"log_loss={rep.log_loss:.4f}  ece={rep.ece:.4f}  n={rep.n}"
    )


@app.command()
def predict(history: Path = typer.Option(..., exists=True),
            card: Path = typer.Option(..., exists=True),
            use_market: bool = False,
            bootstrap: int = 20,
            out_csv: Path | None = None):
    """Fit on ``history`` and score the race card in ``card``."""
    history_df = load_starts_from_csv(history)
    card_df = load_starts_from_csv(card)

    if use_market:
        stack = build_stack_with_market(history_df)
    else:
        stack = build_stack(history_df)

    pred = stack.predict(card_df)

    # --- Uncertainty via baseline bootstrap (cheap + honest) ------------
    if bootstrap > 0:
        bs = BootstrapUncertainty(
            factory=lambda: PlackettLuceBaseline(feature_cols=stack.feature_cols),
            n=bootstrap, prob_col="p_baseline",
        )
        from ..features import build_features
        bs.fit(build_features(history_df))
        draws = bs.predict_draws(build_features(card_df))
        summary = bs.summarise(draws, card_df)
        pred = pred.merge(summary[["race_id", "program_number",
                                     "p_sd", "p_p05", "p_p95"]],
                          on=["race_id", "program_number"], how="left")

    pred = fair_odds_table(pred)
    if "market_share" in card_df.columns:
        pred = edge_table(pred, card_df)

    _print_predictions(pred)
    if out_csv:
        pred.to_csv(out_csv, index=False)
        console.print(f"[green]Wrote predictions to {out_csv}[/green]")


# ---------------------------------------------------------------------------
# Pretty printers
# ---------------------------------------------------------------------------

def _print_folds(df: pd.DataFrame):
    t = Table(title="Walk-forward folds")
    for c in df.columns:
        t.add_column(c)
    for _, r in df.iterrows():
        t.add_row(*[f"{v:.4f}" if isinstance(v, float) else str(v) for v in r])
    console.print(t)


def _print_bucket(label: str, df: pd.DataFrame):
    t = Table(title=f"Metrics by {label}")
    for c in df.columns:
        t.add_column(c)
    for _, r in df.iterrows():
        t.add_row(*[f"{v:.4f}" if isinstance(v, float) else str(v) for v in r])
    console.print(t)


def _print_predictions(df: pd.DataFrame):
    for rid, g in df.groupby("race_id", sort=False):
        t = Table(title=f"Race {rid}")
        show = ["program_number", "horse_id", "p_baseline", "p_boosted",
                "p_ens", "fair_odds"]
        for optional in ("p_sd", "p_p05", "p_p95",
                          "p_market_implied", "edge"):
            if optional in g.columns:
                show.append(optional)
        for c in show:
            t.add_column(c)
        g = g.sort_values("p_ens", ascending=False)
        for _, r in g.iterrows():
            row = []
            for c in show:
                v = r.get(c)
                if isinstance(v, float):
                    if c.startswith("p_") and c != "p_ens_logit":
                        row.append(f"{v:.3%}")
                    else:
                        row.append(f"{v:.3f}")
                else:
                    row.append(str(v))
            t.add_row(*row)
        console.print(t)


if __name__ == "__main__":
    app()
