"""JSON API wrapper for heppa.hippos.fi.

The mobile statistics UI at ``/mobiili/statistics/...`` is a SPA that
calls ``/heppa2_backend/statistics/...`` endpoints directly. Two
different URL patterns are in use:

Horses (confirmed)
------------------
``GET /heppa2_backend/statistics/best/horses``
``?species={L|S|P}&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&limit=N&onlyRegisteredInFinland=true``

Response per horse:
``horseId, name, species, gender, birthCountry, registrationCountry,
birthYear, year, starts, monte, prizeSum, firstPlaces, secondPlaces,
thirdPlaces, photo {...}``

Drivers (confirmed)
-------------------
``GET /heppa2_backend/statistics/risingshape/driver/{startDate}/{endDate}``
``?track=ALL&limit=N&order={WINS|PRIZE_MONEY|...}&horseStarts=true&ponyStarts=false``

Completely different URL shape from horses - dates are path segments
and the query params are about race type rather than species.

Response per person:
``start, wins, secondPlaces, thirdPlaces, priceMoneys, winPercentage,
priceMoneyForStart, winOddsSumForStart, personName, firstName,
lastName, photo {...}, personId``

Trainers (best-guess path, override with HIPPO_TRAINERS_PATH or --path)
-----------------------------------------------------------------------
``GET /heppa2_backend/statistics/risingshape/trainer/{startDate}/{endDate}``

Identical query params and schema to drivers are assumed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal, Optional

import pandas as pd

from .client import HeppaClient
from .discover import fetch_json


DEFAULT_HORSES_PATH = "/heppa2_backend/statistics/best/horses"
# Drivers / trainers use a templated path with dates in the URL segments.
DRIVER_PATH_TEMPLATE = "/heppa2_backend/statistics/risingshape/driver/{start}/{end}"
TRAINER_PATH_TEMPLATE = "/heppa2_backend/statistics/risingshape/trainer/{start}/{end}"
# Per-horse endpoints (confirmed via DevTools).
HORSE_STATS_TEMPLATE = "/heppa2_backend/horse/{horse_id}/stats"
HORSE_STARTS_TEMPLATE = "/heppa2_backend/horse/{horse_id}/starts"

SPECIES_MAP = {
    "warmblood": "L",
    "coldblood": "S",
    "pony": "P",
    "L": "L", "S": "S", "P": "P",
    "all": None,
}

GENDER_MAP = {
    "R": "gelding",     # ruuna
    "O": "stallion",    # ori
    "T": "mare",        # tamma
}

Discipline = Literal["warmblood", "coldblood", "pony", "all"]


@dataclass
class HippoApi:
    """Read-only access to the heppa2_backend JSON endpoints."""

    client: HeppaClient
    horses_path: str = DEFAULT_HORSES_PATH
    driver_template: str = os.getenv("HIPPO_DRIVER_TEMPLATE", DRIVER_PATH_TEMPLATE)
    trainer_template: str = os.getenv("HIPPO_TRAINER_TEMPLATE", TRAINER_PATH_TEMPLATE)

    # ------------------------------------------------------------------
    # Horses
    # ------------------------------------------------------------------
    def top_horses(self, discipline: Discipline = "warmblood",
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None,
                   limit: int = 50,
                   only_registered_in_finland: bool = True,
                   path: Optional[str] = None) -> pd.DataFrame:
        params = _build_horses_params(discipline, start_date, end_date, limit,
                                        only_registered_in_finland)
        data = fetch_json(self.client, path or self.horses_path, params=params)
        return _normalise_horses(_as_list(data))

    # ------------------------------------------------------------------
    # Drivers / trainers (risingshape pattern)
    # ------------------------------------------------------------------
    def top_drivers(self, start_date: str, end_date: str, *,
                    track: str = "ALL", limit: int = 30,
                    order: str = "WINS",
                    horse_starts: bool = True,
                    pony_starts: bool = False,
                    path: Optional[str] = None) -> pd.DataFrame:
        endpoint = path or self.driver_template.format(start=start_date,
                                                         end=end_date)
        params = _build_person_params(track, limit, order,
                                        horse_starts, pony_starts)
        data = fetch_json(self.client, endpoint, params=params)
        return _normalise_people_risingshape(_as_list(data), subject="driver")

    def top_trainers(self, start_date: str, end_date: str, *,
                     track: str = "ALL", limit: int = 30,
                     order: str = "WINS",
                     horse_starts: bool = True,
                     pony_starts: bool = False,
                     path: Optional[str] = None) -> pd.DataFrame:
        endpoint = path or self.trainer_template.format(start=start_date,
                                                          end=end_date)
        params = _build_person_params(track, limit, order,
                                        horse_starts, pony_starts)
        data = fetch_json(self.client, endpoint, params=params)
        return _normalise_people_risingshape(_as_list(data), subject="trainer")

    # ------------------------------------------------------------------
    # Per-horse endpoints
    # ------------------------------------------------------------------
    def horse_stats(self, horse_id: str | int) -> "HorseStats":
        """Return the career / per-year aggregate stats for a single horse."""
        endpoint = HORSE_STATS_TEMPLATE.format(horse_id=horse_id)
        data = fetch_json(self.client, endpoint)
        return HorseStats.from_json(data)

    def horse_starts(self, horse_id: str | int, *,
                      page: int = 1, page_size: int = 20,
                      only_results: bool = True) -> pd.DataFrame:
        """Return the race-by-race history for a single horse.

        Each row is one past start with placing, kilometerTime, distance,
        driverId, trainerId, winOdds etc.
        """
        endpoint = HORSE_STARTS_TEMPLATE.format(horse_id=horse_id)
        params = {
            "pageNumber": str(page),
            "pageSize": str(page_size),
            "onlyResults": "true" if only_results else "false",
        }
        data = fetch_json(self.client, endpoint, params=params)
        return _normalise_horse_starts(_as_list(data))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_horses_params(discipline: Discipline,
                          start_date: Optional[str],
                          end_date: Optional[str],
                          limit: int,
                          only_registered: bool) -> dict[str, str]:
    p: dict[str, str] = {}
    sp = SPECIES_MAP.get(discipline, discipline)
    if sp:
        p["species"] = sp
    if start_date:
        p["startDate"] = start_date
    if end_date:
        p["endDate"] = end_date
    if limit:
        p["limit"] = str(limit)
    if only_registered:
        p["onlyRegisteredInFinland"] = "true"
    return p


# Backwards-compatible alias (older tests may import it)
_build_params = _build_horses_params


def _build_person_params(track: str, limit: int, order: str,
                          horse_starts: bool, pony_starts: bool) -> dict[str, str]:
    return {
        "track": track,
        "limit": str(limit),
        "order": order,
        "horseStarts": str(bool(horse_starts)).lower(),
        "ponyStarts": str(bool(pony_starts)).lower(),
    }


def _as_list(data: Any) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "collection", "items", "rows"):
            v = data.get(key)
            if isinstance(v, list):
                return v
        return [data]
    return []


# ---------------------------------------------------------------------------
# Row normalisation
# ---------------------------------------------------------------------------

def _normalise_horses(rows: list[dict]) -> pd.DataFrame:
    out = []
    for i, r in enumerate(rows, start=1):
        starts = _safe_int(r.get("starts"))
        wins = _safe_int(r.get("firstPlaces"))
        seconds = _safe_int(r.get("secondPlaces"))
        thirds = _safe_int(r.get("thirdPlaces"))
        earnings = _safe_int(r.get("prizeSum"))
        out.append({
            "rank": i,
            "horse_id": r.get("horseId"),
            "name": r.get("name"),
            "species": r.get("species"),
            "gender": GENDER_MAP.get(r.get("gender"), r.get("gender")),
            "birth_year": _safe_int(r.get("birthYear")),
            "birth_country": r.get("birthCountry"),
            "registration_country": r.get("registrationCountry"),
            "starts": starts,
            "wins": wins,
            "seconds": seconds,
            "thirds": thirds,
            "win_pct": _pct(wins, starts),
            "place_pct": _pct((wins or 0) + (seconds or 0) + (thirds or 0), starts),
            "earnings_eur": earnings,
            "monte_code": r.get("monte"),
        })
    return pd.DataFrame(out)


def _normalise_people_risingshape(rows: list[dict], *, subject: str) -> pd.DataFrame:
    """Normalise the ``risingshape/{driver|trainer}`` response.

    Each row in the response carries:
      start, wins, secondPlaces, thirdPlaces, priceMoneys,
      winPercentage, priceMoneyForStart, winOddsSumForStart,
      personName, firstName, lastName, personId, photo
    """
    out = []
    for i, r in enumerate(rows, start=1):
        starts = _safe_int(r.get("start") or r.get("starts"))
        wins = _safe_int(r.get("wins") or r.get("firstPlaces"))
        seconds = _safe_int(r.get("secondPlaces"))
        thirds = _safe_int(r.get("thirdPlaces"))
        earnings = _safe_int(r.get("priceMoneys") or r.get("prizeSum"))
        eur_per_start = _safe_float(r.get("priceMoneyForStart"))
        win_pct = _safe_float(r.get("winPercentage"))
        win_odds_per_start = _safe_float(r.get("winOddsSumForStart"))
        out.append({
            "rank": i,
            f"{subject}_id": r.get("personId") or r.get(f"{subject}Id"),
            subject: r.get("personName") or r.get("name") or r.get("fullName"),
            "first_name": r.get("firstName"),
            "last_name": r.get("lastName"),
            "starts": starts,
            "wins": wins,
            "seconds": seconds,
            "thirds": thirds,
            "win_pct": win_pct if win_pct is not None else _pct(wins, starts),
            "place_pct": _pct((wins or 0) + (seconds or 0) + (thirds or 0), starts),
            "earnings_eur": earnings,
            "earnings_per_start": eur_per_start,
            "win_odds_per_start": win_odds_per_start,
        })
    return pd.DataFrame(out)


# Backwards-compatible alias
_normalise_people = _normalise_people_risingshape


# ---------------------------------------------------------------------------
# Record-time parsing (Finnish harness racing format)
# ---------------------------------------------------------------------------

def parse_km_time(s: str | None) -> Optional[float]:
    """Parse a kilometer time into seconds.

    Accepts both the short form ``"14,9"`` (1:14.9 per km, a.k.a.
    shortKilometerTime) and the long form ``"1.14.9"`` (minute.second.tenth).
    Returns seconds per kilometre, e.g. 74.9.
    """
    if s is None or s == "" or s == "-":
        return None
    s = str(s).strip()
    # Long form: "1.14.9" -> 1 * 60 + 14.9
    if s.count(".") == 2:
        try:
            m, sec, tenth = s.split(".")
            return float(m) * 60 + float(sec) + float(tenth) / 10.0
        except ValueError:
            return None
    # Short form: "14,9" or "08,3" -> 60 + 14.9
    s = s.replace(",", ".")
    try:
        v = float(s)
        # Records < 60s are implicitly "below one minute per km": add 60s
        if v < 60:
            v += 60
        return v
    except ValueError:
        return None


def parse_total_time(s: str | None) -> Optional[float]:
    """Parse a total race time into seconds. Format: ``"2.40.3"``."""
    if s is None or s == "" or s == "-":
        return None
    try:
        parts = str(s).split(".")
        if len(parts) == 3:
            m, sec, tenth = parts
            return float(m) * 60 + float(sec) + float(tenth) / 10.0
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Horse stats (career + yearly aggregates)
# ---------------------------------------------------------------------------

@dataclass
class HorseStats:
    horse_id: str
    total: dict
    yearly: pd.DataFrame
    monte_total: dict
    monte_yearly: pd.DataFrame

    @classmethod
    def from_json(cls, data: dict) -> "HorseStats":
        return cls(
            horse_id=str(data.get("id", "")),
            total=_normalise_stats_row(data.get("total") or {}),
            yearly=_stats_df(data.get("stats") or []),
            monte_total=_normalise_stats_row(data.get("monteTotal") or {}),
            monte_yearly=_stats_df(data.get("monteStats") or []),
        )

    def year(self, year: int | str) -> Optional[dict]:
        if self.yearly.empty:
            return None
        m = self.yearly[self.yearly["year"] == str(year)]
        return m.iloc[0].to_dict() if not m.empty else None

    def recent_years(self, n: int = 3) -> pd.DataFrame:
        if self.yearly.empty:
            return self.yearly
        return self.yearly.sort_values("year", ascending=False).head(n).reset_index(drop=True)


def _normalise_stats_row(row: dict) -> dict:
    return {
        "year": row.get("year"),
        "starts": _safe_int(row.get("starts")) or 0,
        "wins": _safe_int(row.get("firstPlaces")) or 0,
        "seconds": _safe_int(row.get("secondPlaces")) or 0,
        "thirds": _safe_int(row.get("thirdPlaces")) or 0,
        "gallops": _safe_int(row.get("gallops")) or 0,
        "disqualifications": _safe_int(row.get("disqualifications")) or 0,
        "win_pct": _safe_float(row.get("winningPercent")),
        "place_pct": _safe_float(row.get("placementPercent")),
        "gallop_pct": _safe_float(row.get("gallopPercentage")),
        "disqualification_pct": _safe_float(row.get("disqualificationPercentage")),
        "earnings_eur": _safe_int(row.get("priceMoney")) or 0,
        "earnings_per_start": _safe_float(row.get("priceMoneyPerStart")),
        "car_record_s": parse_km_time(row.get("carRecord")),
        "car_record_type": row.get("carRecordType") or None,
        "record_s": parse_km_time(row.get("record")),
        "record_type": row.get("recordType") or None,
        "best_record_of_year": row.get("bestRecordOfYear"),
        "best_record_ever": row.get("bestRecordOfAllTime"),
    }


def _stats_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([_normalise_stats_row(r) for r in rows])


# ---------------------------------------------------------------------------
# Horse starts (race-by-race history)
# ---------------------------------------------------------------------------

def _normalise_horse_starts(rows: list[dict]) -> pd.DataFrame:
    out = []
    for r in rows:
        placing_raw = r.get("placing")
        placing = _safe_int(placing_raw)
        # placing == 0 is returned for upcoming starts that haven't run yet
        did_run = placing is not None and placing > 0
        out.append({
            "date": r.get("date"),
            "track_code": r.get("trackCode"),
            "race_number": _safe_int(r.get("startNumber")),
            "start_form": r.get("startForm"),
            "is_monte": bool(r.get("monte", False)),
            "program_number": _safe_int(r.get("programNumber")),
            "post_position": _safe_int(r.get("lane")),
            "distance_m": _safe_int(r.get("distance")),
            "distance_code": r.get("distanceCode"),
            "placing": placing if did_run else None,
            "did_run": did_run,
            "absent": bool(r.get("absent", False)),
            "gallop": bool(r.get("gallop", False)),
            "earnings_eur": _safe_int(r.get("price")) or 0,
            "win_odds": _safe_float(r.get("winOdds") or r.get("winOddsStr")),
            "total_time_s": parse_total_time(r.get("totalTime")),
            "km_time_s": parse_km_time(r.get("kilometerTime")
                                         or r.get("shortKilometerTime")),
            "horse_id": r.get("horseId"),
            "horse_name": r.get("horseName"),
            "horse_breed": r.get("horseBreed"),
            "driver_id": r.get("driverId"),
            "driver_name": r.get("driverName"),
            "trainer_id": r.get("trainerId"),
            "trainer_name": r.get("trainerName"),
            "shoes_front": r.get("shoesFront"),
            "shoes_back": r.get("shoesBack"),
            "american_sulky": r.get("americanSulkyKEX"),
            "start_type": r.get("startType"),
            "finnish_track": bool(r.get("finnishTrack", True)),
            "tototv_link": r.get("tototvLink"),
        })
    df = pd.DataFrame(out)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Feature extraction for race_model
# ---------------------------------------------------------------------------

def to_race_model_features(starts_df: pd.DataFrame,
                            last_n: int = 6,
                            reference_date: Optional[str] = None) -> dict:
    """Convert a horse_starts() DataFrame into race_model prior-* lists.

    Returns a dict with keys aligned to :mod:`race_model.data.schemas.Start`:

      prior_finishes, prior_km_times, prior_earnings,
      prior_opponent_strengths, days_since_last_start, gallop_risk

    Only completed starts (``did_run=True``) are used. The most recent
    ``last_n`` rows are taken. ``prior_opponent_strengths`` is
    approximated from the horse's own ``winOdds`` each race: lower odds
    mean a stronger field (opposing is easier — the horse was the
    favourite). We use ``-log(1/odds)`` so higher = stronger opposition,
    i.e. the horse was an underdog in a strong field.
    """
    if starts_df.empty:
        return {"prior_finishes": [], "prior_km_times": [],
                "prior_earnings": [], "prior_opponent_strengths": [],
                "days_since_last_start": None, "gallop_risk": None}

    df = starts_df[starts_df["did_run"] == True].sort_values("date", ascending=False).head(last_n)
    if df.empty:
        return {"prior_finishes": [], "prior_km_times": [],
                "prior_earnings": [], "prior_opponent_strengths": [],
                "days_since_last_start": None, "gallop_risk": None}

    import numpy as np

    # Opponent strength proxy: how much of an underdog was the horse on
    # average? log(odds) is high when the horse was a longshot.
    odds = df["win_odds"].astype(float)
    opp_strength = np.where(odds.notna() & (odds > 1.0), np.log(odds), 0.0)

    # Gallop risk = fraction of recent starts where the horse broke stride.
    gallop_risk = float(df["gallop"].astype(bool).mean())

    # Days since last start (from reference_date, default today).
    ref = pd.to_datetime(reference_date) if reference_date else pd.Timestamp.utcnow().normalize()
    last_date = df["date"].iloc[0]
    days = int((ref - last_date).days) if pd.notna(last_date) else None

    return {
        "prior_finishes": df["placing"].fillna(0).astype(int).tolist(),
        "prior_km_times": df["km_time_s"].dropna().astype(float).tolist(),
        "prior_earnings": df["earnings_eur"].fillna(0).astype(int).tolist(),
        "prior_opponent_strengths": list(opp_strength),
        "days_since_last_start": days,
        "gallop_risk": gallop_risk,
    }


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _safe_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).replace("\u00A0", "").replace(" ", "")))
    except (TypeError, ValueError):
        return None


def _safe_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        s = str(v).replace("\u00A0", "").replace(" ", "").replace(",", ".")
        return float(s)
    except (TypeError, ValueError):
        return None


def _pct(num: Optional[int], denom: Optional[int]) -> Optional[float]:
    if not denom or num is None:
        return None
    return round(100.0 * num / denom, 2)
