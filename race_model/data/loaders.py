"""CSV/JSON loaders and a configurable synthetic-history generator.

The synthetic generator emits *consistent* data: each horse has a latent
ability that evolves slowly over time, finish positions are sampled from
a Plackett-Luce model over horse abilities + race-specific factors, and
km times are drawn to match the sampled ordering. Market shares are
generated with a mild favourite-longshot bias relative to the latent
winning probabilities, enabling the ``with_market`` pipeline to find
edge without trivially learning the answer.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


COLUMNS_REQUIRED = {"race_id", "race_date", "program_number", "horse_id"}


def load_starts_from_csv(path: str | Path) -> pd.DataFrame:
    """Load a long-format starts CSV into a DataFrame.

    Pipe-separated list columns (``prior_finishes``, ``prior_km_times``,
    ``prior_earnings``, ``prior_opponent_strengths``) are parsed
    automatically.
    """
    df = pd.read_csv(path, parse_dates=["race_date"])
    missing = COLUMNS_REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    df["race_date"] = df["race_date"].dt.date

    for c in ("prior_finishes", "prior_km_times",
              "prior_earnings", "prior_opponent_strengths"):
        if c in df.columns:
            df[c] = df[c].apply(_parse_list)
    return df


def load_starts_from_json(path: str | Path) -> pd.DataFrame:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return pd.DataFrame(data)


def _parse_list(v):
    if isinstance(v, list):
        return v
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return []
    s = str(v)
    if not s:
        return []
    out = []
    for x in s.split("|"):
        if x == "":
            continue
        try:
            out.append(float(x) if "." in x else int(x))
        except ValueError:
            pass
    return out


# ---------------------------------------------------------------------------
# Synthetic history generator
# ---------------------------------------------------------------------------

def generate_history(n_races: int = 300,
                     n_horses: int = 120,
                     start_date: date = date(2023, 1, 1),
                     seed: int = 42) -> pd.DataFrame:
    """Generate a realistic synthetic training history.

    Returns a DataFrame of starts with ``finished_position`` populated,
    including recent-form columns and a mildly-biased ``market_share``.
    """
    rng = np.random.default_rng(seed)

    ability = rng.normal(0.0, 1.0, size=n_horses)        # latent quality
    driver_quality = rng.normal(0.0, 0.4, size=60)
    trainer_quality = rng.normal(0.0, 0.3, size=80)

    # Per-horse history buffers for feature generation
    hist_finishes: list[list[int]] = [[] for _ in range(n_horses)]
    hist_kms: list[list[float]] = [[] for _ in range(n_horses)]
    hist_earnings: list[list[float]] = [[] for _ in range(n_horses)]
    hist_opp: list[list[float]] = [[] for _ in range(n_horses)]
    last_start_date: list[date | None] = [None for _ in range(n_horses)]

    rows: list[dict] = []
    for r in range(n_races):
        race_date_r = start_date + timedelta(days=int(r * rng.uniform(0.3, 0.8)))
        n_run = int(rng.integers(8, 15))
        starters = rng.choice(n_horses, size=n_run, replace=False)
        race_id = f"R{r + 1:04d}"
        distance_m = int(rng.choice([1609, 2100, 2600, 3100]))
        start_type = str(rng.choice(["volt", "auto"], p=[0.55, 0.45]))
        track_cond = str(rng.choice(["normal", "soft", "hard"], p=[0.7, 0.15, 0.15]))

        # Race-specific strength = latent + drift + driver + small noise
        drift = 0.02 * r / n_races
        drivers = rng.integers(0, len(driver_quality), size=n_run)
        trainers = rng.integers(0, len(trainer_quality), size=n_run)
        strengths = (ability[starters] + drift
                     + driver_quality[drivers]
                     + trainer_quality[trainers]
                     + rng.normal(0, 0.3, size=n_run))

        # Post-position penalty (outer gates harder on volt starts)
        if start_type == "volt":
            strengths = strengths - 0.05 * (np.arange(n_run) - n_run / 2) * (np.arange(n_run) > n_run / 2)

        # Plackett-Luce sampling: iteratively pick the next finisher
        logits = strengths.copy()
        positions = np.zeros(n_run, dtype=int)
        idx_alive = list(range(n_run))
        for pos in range(n_run):
            p = np.exp(logits[idx_alive] - np.max(logits[idx_alive]))
            p = p / p.sum()
            pick = rng.choice(idx_alive, p=p)
            positions[pick] = pos + 1
            idx_alive.remove(pick)

        # Market shares: softmax of strengths with a mild bias
        market = np.exp(strengths * rng.uniform(1.1, 1.4))
        market = market / market.sum()

        # Finish times rank-aligned with positions
        base_time = 72.0 + (distance_m / 2100.0) * 5.0
        km_times = base_time + 0.5 * (positions - 1) + rng.normal(0, 0.2, size=n_run)

        for i in range(n_run):
            h = int(starters[i])
            d = int(drivers[i])
            t = int(trainers[i])
            days_since = None
            if last_start_date[h] is not None:
                days_since = (race_date_r - last_start_date[h]).days

            rows.append({
                "race_id": race_id,
                "race_date": race_date_r,
                "track": f"T{int(rng.integers(1, 5))}",
                "distance_m": distance_m,
                "start_type": start_type,
                "track_condition": track_cond,
                "race_class": str(rng.choice(["A", "B", "C"])),
                "program_number": i + 1,
                "horse_id": f"H{h:04d}",
                "driver_id": f"D{d:03d}",
                "trainer_id": f"TR{t:03d}",
                "post_position": i + 1,
                "carried_weight_kg": float(round(rng.uniform(62, 68), 1)),
                "prior_finishes": list(hist_finishes[h][-6:]),
                "prior_km_times": list(hist_kms[h][-6:]),
                "prior_earnings": list(hist_earnings[h][-6:]),
                "prior_opponent_strengths": list(hist_opp[h][-6:]),
                "days_since_last_start": days_since,
                "gallop_risk": float(np.clip(rng.beta(1.2, 20), 0, 1)),
                "speed_rating": float(round(80 + ability[h] * 5 + rng.normal(0, 1), 2)),
                "class_rating": float(round(80 + ability[h] * 4.5 + rng.normal(0, 1.2), 2)),
                "stamina_rating": float(round(80 + ability[h] * 4.0 + rng.normal(0, 1.5), 2)),
                "equipment_change": bool(rng.random() < 0.08),
                "shoeing_change": bool(rng.random() < 0.05),
                "market_share": float(market[i]),
                "finished_position": int(positions[i]),
                "did_not_finish": False,
            })
            # Update per-horse history after emitting the row
            hist_finishes[h].append(int(positions[i]))
            hist_kms[h].append(float(km_times[i]))
            hist_earnings[h].append(float(round(max(5000 - (positions[i] - 1) * 700, 200), 0)))
            # Opponent strength proxy: median latent ability of other runners
            other_mask = np.ones(n_run, dtype=bool)
            other_mask[i] = False
            hist_opp[h].append(float(np.median(ability[starters[other_mask]])))
            last_start_date[h] = race_date_r

    return pd.DataFrame(rows)


def save_history_csv(df: pd.DataFrame, path: str | Path) -> None:
    """Serialise a history DataFrame to CSV with pipe-encoded list columns."""
    out = df.copy()
    for c in ("prior_finishes", "prior_km_times",
              "prior_earnings", "prior_opponent_strengths"):
        if c in out.columns:
            out[c] = out[c].apply(lambda v: "|".join(str(x) for x in (v or [])))
    out.to_csv(path, index=False)
