"""Data loading and demo-data generation.

The ingestion layer is deliberately pluggable. Today it supports:

* CSV / JSON files following the project schema.
* An in-memory demo generator used by tests and the Streamlit UI.

To add a real Veikkaus-compliant data source, implement ``RaceCardLoader``
and wire it into :func:`load_race_card`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Protocol

import numpy as np
import pandas as pd

from .schemas import Horse, PoolShare, Race, RaceCard, StartType


class RaceCardLoader(Protocol):
    def load(self, source: str | Path) -> RaceCard: ...


# ---------------------------------------------------------------------------
# CSV / JSON loaders
# ---------------------------------------------------------------------------

REQUIRED_CSV_COLS = {"race_id", "race_number", "track", "distance_m", "program_number", "name"}


def load_race_card_from_csv(path: str | Path, *, product: str = "toto75",
                            jackpot: float = 0.0, total_pool: float = 0.0,
                            takeout: float | None = None,
                            date: str = "", venue: str = "") -> RaceCard:
    """Load a race card from a long-format CSV.

    Each row represents one horse in one race. Columns are matched loosely
    (missing optional columns are filled with ``None``). See
    ``data/sample/sample_toto75.csv`` for a minimal example.
    """
    df = pd.read_csv(path)
    missing = REQUIRED_CSV_COLS - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    races: list[Race] = []
    for race_id, g in df.groupby("race_id", sort=False):
        g = g.sort_values("program_number")
        horses = [_row_to_horse(r) for r in g.to_dict(orient="records")]
        first = g.iloc[0]
        races.append(Race(
            race_id=str(race_id),
            race_number=int(first["race_number"]),
            track=str(first["track"]),
            distance_m=int(first["distance_m"]),
            start_type=StartType(first.get("start_type", "volt") or "volt"),
            race_class=first.get("race_class"),
            surface=first.get("surface"),
            weather=first.get("weather"),
            track_condition=first.get("track_condition"),
            horses=horses,
        ))

    return RaceCard(
        product=product, date=date, venue=venue,
        races=races, jackpot=jackpot, total_pool=total_pool, takeout=takeout,
    )


def load_race_card_from_json(path: str | Path) -> RaceCard:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return RaceCard.model_validate(data)


def load_race_card(source: str | Path, **kwargs) -> RaceCard:
    """Dispatch loader based on file extension."""
    p = Path(source)
    if p.suffix.lower() == ".json":
        return load_race_card_from_json(p)
    if p.suffix.lower() in {".csv", ".tsv"}:
        return load_race_card_from_csv(p, **kwargs)
    raise ValueError(f"Unsupported file type: {p.suffix}")


def _row_to_horse(row: dict) -> Horse:
    def _parse_list(val, cast):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return []
        if isinstance(val, list):
            return [cast(x) for x in val]
        return [cast(x) for x in str(val).split("|") if x != ""]

    return Horse(
        program_number=int(row["program_number"]),
        name=str(row["name"]),
        driver=row.get("driver"),
        trainer=row.get("trainer"),
        post_position=_opt_int(row.get("post_position")),
        recent_finishes=_parse_list(row.get("recent_finishes"), int),
        recent_kilometer_times=_parse_list(row.get("recent_kilometer_times"), float),
        recent_earnings=_parse_list(row.get("recent_earnings"), float),
        speed_rating=_opt_float(row.get("speed_rating")),
        class_rating=_opt_float(row.get("class_rating")),
        stamina_rating=_opt_float(row.get("stamina_rating")),
        gallop_risk=_opt_float(row.get("gallop_risk")),
        days_since_last_start=_opt_int(row.get("days_since_last_start")),
        equipment_change=_opt_bool(row.get("equipment_change")),
        shoeing_change=_opt_bool(row.get("shoeing_change")),
        pool_percentage=_opt_float(row.get("pool_percentage")),
        published_odds=_opt_float(row.get("published_odds")),
        finished_position=_opt_int(row.get("finished_position")),
        did_not_finish=bool(row.get("did_not_finish", False)),
    )


def _opt_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _opt_int(v):
    f = _opt_float(v)
    return None if f is None else int(f)


def _opt_bool(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    s = str(v).strip().lower()
    if s in {"1", "true", "t", "yes", "y"}:
        return True
    if s in {"0", "false", "f", "no", "n"}:
        return False
    return None


# ---------------------------------------------------------------------------
# Pool shares
# ---------------------------------------------------------------------------

def load_pool_shares_from_csv(path: str | Path) -> list[PoolShare]:
    """Load per-horse Veikkaus pool percentages from a CSV.

    Expected columns: ``race_id``, ``program_number``, ``share`` (in 0-1 or
    0-100). Values >1 are automatically divided by 100.
    """
    df = pd.read_csv(path)
    shares = []
    for _, r in df.iterrows():
        s = float(r["share"])
        if s > 1.0:
            s /= 100.0
        shares.append(PoolShare(race_id=str(r["race_id"]),
                                program_number=int(r["program_number"]),
                                share=s))
    return shares


# ---------------------------------------------------------------------------
# Demo data generator
# ---------------------------------------------------------------------------

def _rng(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(seed)


def _sample_recent(rng: np.random.Generator, base_rating: float) -> dict:
    n = int(rng.integers(3, 7))
    # Lower rating -> lower finishes
    mean_pos = max(1.0, 6.5 - base_rating / 20.0)
    fins = list(np.clip(rng.normal(mean_pos, 2.0, size=n), 1, 12).round().astype(int))
    km_times = list(np.round(rng.normal(79.0 - base_rating / 25.0, 0.8, size=n), 1))
    earn = list(np.round(np.abs(rng.normal(400 + base_rating * 8, 300, size=n)), 0))
    return {"recent_finishes": fins, "recent_kilometer_times": km_times,
            "recent_earnings": earn}


def generate_demo_race(race_id: str, race_number: int, n_horses: int = 12,
                       seed: int | None = None) -> Race:
    """Generate a synthetic but plausible race."""
    rng = _rng(seed)
    # A latent "strength" per horse on a 0-100 scale
    strengths = rng.uniform(20, 95, size=n_horses)
    # Biased market share: favourites get a bit of extra love
    raw = np.exp(strengths / 12)
    shares = raw / raw.sum()
    # Simulate favourite-longshot bias: push mass slightly to favourites
    shares = shares ** 1.15
    shares = shares / shares.sum()

    horses: list[Horse] = []
    for i in range(n_horses):
        s = float(strengths[i])
        recent = _sample_recent(rng, s)
        horses.append(Horse(
            program_number=i + 1,
            name=f"Horse_{race_number}_{i + 1}",
            driver=f"Driver_{rng.integers(1, 30)}",
            trainer=f"Trainer_{rng.integers(1, 40)}",
            post_position=i + 1,
            speed_rating=round(s + float(rng.normal(0, 3)), 2),
            class_rating=round(s * 0.9 + float(rng.normal(0, 5)), 2),
            stamina_rating=round(s * 0.95 + float(rng.normal(0, 4)), 2),
            gallop_risk=float(np.clip(rng.beta(1.2, 20), 0, 1)),
            days_since_last_start=int(rng.integers(7, 60)),
            equipment_change=bool(rng.random() < 0.1),
            shoeing_change=bool(rng.random() < 0.08),
            pool_percentage=round(float(shares[i]) * 100, 2),
            **recent,
        ))
    return Race(
        race_id=race_id, race_number=race_number,
        track="KuopioDemo", distance_m=2100,
        start_type=StartType.VOLT, race_class="Demo",
        horses=horses,
    )


def generate_demo_card(product: str = "toto75", n_races: int = 7,
                       jackpot: float = 250_000.0, total_pool: float = 500_000.0,
                       seed: int | None = 42) -> RaceCard:
    """Generate a complete synthetic Toto card."""
    races = [
        generate_demo_race(f"R{i + 1}", i + 1, n_horses=int(np.random.default_rng(seed + i).integers(10, 15)),
                           seed=seed + i)
        for i in range(n_races)
    ]
    return RaceCard(
        product=product, date="2026-04-17", venue="DemoTrack",
        races=races, jackpot=jackpot, total_pool=total_pool, takeout=0.25,
    )


def race_card_to_dataframe(card: RaceCard) -> pd.DataFrame:
    """Flatten a race card to a long-format DataFrame, useful for features."""
    rows: list[dict] = []
    for race in card.races:
        for h in race.horses:
            rows.append({
                "race_id": race.race_id,
                "race_number": race.race_number,
                "track": race.track,
                "distance_m": race.distance_m,
                "start_type": race.start_type.value,
                "race_class": race.race_class,
                "program_number": h.program_number,
                "name": h.name,
                "driver": h.driver,
                "trainer": h.trainer,
                "post_position": h.post_position,
                "speed_rating": h.speed_rating,
                "class_rating": h.class_rating,
                "stamina_rating": h.stamina_rating,
                "gallop_risk": h.gallop_risk,
                "days_since_last_start": h.days_since_last_start,
                "equipment_change": h.equipment_change,
                "shoeing_change": h.shoeing_change,
                "pool_percentage": h.pool_percentage,
                "published_odds": h.published_odds,
                "recent_finishes": h.recent_finishes,
                "recent_kilometer_times": h.recent_kilometer_times,
                "recent_earnings": h.recent_earnings,
                "finished_position": h.finished_position,
                "did_not_finish": h.did_not_finish,
            })
    return pd.DataFrame(rows)
