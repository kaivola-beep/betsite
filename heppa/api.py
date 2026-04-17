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
