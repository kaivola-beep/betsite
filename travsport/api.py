"""High-level Svensk Travsport endpoints.

Confirmed endpoint (from DevTools)
----------------------------------
``GET /services/race/{raceId}/stats``

``raceId`` is the concatenation ``{date}_{trackNumber}_{raceNumber}``,
e.g. ``2026-04-17_18_1`` is Halmstad (track 18) race 1 on 17 April 2026.
Use :func:`make_race_id` to build it cleanly.

The response is a dict keyed by ``program_number`` (string). Every
entry contains:

* ``startNr``
* ``pastPerformances``: list of previous starts with
  ``formattedPlace``, ``raceDayDate`` (.NET ``/Date(ms)/``),
  ``trackCode``, ``raceNr``, ``distance``, ``formattedTime``
  (e.g. ``"22,4"`` = 1:22.4 per km), ``odds``,
  ``formattedResult`` (``"1"``..``"15"``, ``"0"``, ``"k"``, ``"p"``),
  ``startMethod``, ``driverFullName``, ``raceType``
  (``"V"`` = race, ``"K"`` = qualifier, ``"P"`` = prov/test).
* ``horseStats``: yearly + ``"Life"`` aggregate rows with
  ``earningSum`` (SEK), ``first``, ``second``, ``third``, ``nrOfStarts``.

Not yet confirmed (pending DevTools discovery)
---------------------------------------------
* startlist endpoint with horse names, driver IDs, market odds
* horse profile (pedigree, records, birth year)

Until those are known, ``travsport`` covers only the race-level stats
endpoint, which is already enough for form-index, km-time and
opponent-odds features when cross-referenced with the Veikkaus card
runners (joined by ``program_number``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from .client import TravsportClient


RACE_STATS_TEMPLATE = "/services/race/{race_id}/stats"

# Result codes that mean "completed race" (vs qualifier/prov tests)
COMPLETED_RESULT_REGEX = re.compile(r"^\d+$")   # "1", "12", "0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_race_id(date: str, track_number: int | str, race_number: int | str) -> str:
    """Return the canonical ``YYYY-MM-DD_{track}_{race}`` race ID."""
    return f"{date}_{track_number}_{race_number}"


def parse_dotnet_date(s: str | None) -> Optional[datetime]:
    """Parse ``/Date(1690848000000)/`` style .NET dates."""
    if not s:
        return None
    m = re.search(r"(-?\d+)", s)
    if not m:
        return None
    ms = int(m.group(1))
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def parse_km_time(s: str | None) -> Optional[float]:
    """Parse a km time. Swedish format ``"22,4"`` = 1:22.4 / km."""
    if s is None or s in ("", "-", "‒"):
        return None
    # Strip trailing alpha characters (record-type tags) just in case
    m = re.match(r"^[0-9.,]+", str(s).strip())
    if not m:
        return None
    val = m.group(0).replace(",", ".")
    try:
        v = float(val)
    except ValueError:
        return None
    if v < 60:
        v += 60
    return v


def _safe_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v)))
    except (TypeError, ValueError):
        return None


def _safe_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@dataclass
class TravsportApi:
    client: TravsportClient

    def race_stats(self, race_id: str) -> "RaceStats":
        """Return parsed stats for every horse in a race."""
        endpoint = RACE_STATS_TEMPLATE.format(race_id=race_id)
        data = self.client.get_json(endpoint)
        return RaceStats.from_json(race_id, data)


# ---------------------------------------------------------------------------
# Structured containers
# ---------------------------------------------------------------------------

@dataclass
class RaceStats:
    race_id: str
    past_performances: pd.DataFrame
    """Long-format: one row per (horse, past start)."""

    horse_summary: pd.DataFrame
    """One row per horse with lifetime + last-year aggregates."""

    @classmethod
    def from_json(cls, race_id: str, data: dict) -> "RaceStats":
        stats_block = data.get("stats") or {}
        pp_rows: list[dict] = []
        summary_rows: list[dict] = []

        for pn_key, block in stats_block.items():
            try:
                program_number = int(block.get("startNr") or pn_key)
            except (TypeError, ValueError):
                continue

            for p in block.get("pastPerformances") or []:
                result = p.get("formattedResult") or ""
                place_str = p.get("formattedPlace") or ""
                # Only keep rows from actual races (V), not qualifiers (K/P)
                raw_race_type = p.get("raceType") or ""
                pp_rows.append({
                    "race_id": race_id,
                    "program_number": program_number,
                    "prev_date": parse_dotnet_date(p.get("raceDayDate")),
                    "prev_track_code": p.get("trackCode"),
                    "prev_race_number": _safe_int(p.get("raceNr")),
                    "prev_distance_m": _safe_int(p.get("distance")),
                    "prev_start_method": p.get("startMethod"),
                    "prev_race_type": raw_race_type,
                    "prev_driver": p.get("driverFullName"),
                    "placing": _safe_int(place_str) if place_str.isdigit() else None,
                    "km_time_s": parse_km_time(p.get("formattedTime")),
                    "win_odds": _safe_float(p.get("odds"))
                    if p.get("odds") not in (None, "", "gdk", "ejg") else None,
                    "is_competition": bool(COMPLETED_RESULT_REGEX.match(result)
                                              or raw_race_type == "V"),
                    "disqualified": bool(p.get("disqualified", False)),
                    "scratched": bool(p.get("scratched", False)),
                })

            summary_by_period = {s.get("period"): s
                                  for s in (block.get("horseStats") or [])}
            life = summary_by_period.get("Life") or {}
            # Most recent year that actually has starts; fall back to the
            # most recent year listed if none have starts.
            year_rows = [(yr, row) for yr, row in summary_by_period.items()
                          if yr not in ("Life", None) and str(yr).isdigit()]
            year_rows.sort(key=lambda x: int(x[0]), reverse=True)
            last_year = None
            last_year_row: dict = {}
            for yr, row in year_rows:
                if (_safe_int(row.get("nrOfStarts")) or 0) > 0:
                    last_year = yr
                    last_year_row = row
                    break
            if last_year is None and year_rows:
                last_year, last_year_row = year_rows[0]
            summary_rows.append({
                "race_id": race_id,
                "program_number": program_number,
                "life_starts": _safe_int(life.get("nrOfStarts")) or 0,
                "life_wins": _safe_int(life.get("first")) or 0,
                "life_seconds": _safe_int(life.get("second")) or 0,
                "life_thirds": _safe_int(life.get("third")) or 0,
                "life_earnings_sek": _safe_float(life.get("earningSum")) or 0.0,
                "last_year": last_year,
                "last_year_starts": _safe_int((last_year_row or {}).get("nrOfStarts")) or 0,
                "last_year_wins": _safe_int((last_year_row or {}).get("first")) or 0,
                "last_year_earnings_sek": _safe_float(
                    (last_year_row or {}).get("earningSum")) or 0.0,
            })

        pp_df = pd.DataFrame(pp_rows)
        if not pp_df.empty:
            pp_df = pp_df.sort_values(["program_number", "prev_date"],
                                        ascending=[True, False]).reset_index(drop=True)
        summary_df = pd.DataFrame(summary_rows)
        if not summary_df.empty:
            summary_df = summary_df.sort_values("program_number").reset_index(drop=True)
        return cls(race_id=race_id,
                   past_performances=pp_df,
                   horse_summary=summary_df)

    # ------------------------------------------------------------------
    def to_race_model_features(self, *, last_n: int = 6,
                                reference_date: Optional[str] = None) -> pd.DataFrame:
        """Return a DataFrame keyed by program_number with race_model
        prior_* lists.

        Only rows flagged as ``is_competition`` (real race types, not
        qualifiers) contribute to the priors. Opponent-strength is
        approximated with ``log(win_odds)`` per past start — higher
        means the horse was a longshot in a stronger field.
        """
        pp = self.past_performances
        out: list[dict] = []
        ref = (pd.to_datetime(reference_date, utc=True) if reference_date
               else pd.Timestamp.now(tz="UTC").normalize())
        for pn, group in pp.groupby("program_number"):
            g = group[group["is_competition"]].head(last_n)
            if g.empty:
                out.append({"program_number": pn,
                             "prior_finishes": [], "prior_km_times": [],
                             "prior_earnings": [],
                             "prior_opponent_strengths": [],
                             "days_since_last_start": None,
                             "gallop_risk": None})
                continue
            odds = g["win_odds"].astype(float)
            opp_strength = np.where(odds.notna() & (odds > 1.0),
                                      np.log(odds.fillna(1.0)), 0.0)
            last_date = g["prev_date"].iloc[0]
            days = (int((ref - last_date).days)
                    if pd.notna(last_date) else None)
            out.append({
                "program_number": pn,
                "prior_finishes": g["placing"].fillna(0).astype(int).tolist(),
                "prior_km_times": g["km_time_s"].dropna().astype(float).tolist(),
                "prior_earnings": [],      # not exposed per-start by Travsport
                "prior_opponent_strengths": list(opp_strength),
                "days_since_last_start": days,
                "gallop_risk": float(g["disqualified"].astype(bool).mean()),
            })
        return pd.DataFrame(out)
