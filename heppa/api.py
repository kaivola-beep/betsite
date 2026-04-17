"""JSON API wrapper for heppa.hippos.fi.

The mobile statistics UI at ``/mobiili/statistics/...`` is a SPA that
calls the backend at ``/heppa2_backend/statistics/best/...`` and
renders the JSON. This module calls that JSON endpoint directly, which
is both faster and less fragile than HTML scraping.

Confirmed endpoint
------------------
``GET https://heppa.hippos.fi/heppa2_backend/statistics/best/horses``

Query parameters observed in the SPA:

* ``onlyRegisteredInFinland=true`` — only horses registered in Finland.
* ``species=L`` (lämminverinen), ``S`` (suomenhevonen), ``P`` (pony).
* ``limit=10`` (etc.)
* ``startDate=YYYY-MM-DD``, ``endDate=YYYY-MM-DD``.

Response shape
--------------
An array of records with the following fields (all strings; numeric
fields are coerced in :func:`_normalise_horses`):

``horseId, name, species, gender, birthCountry, registrationCountry,
birthYear, year, starts, monte, prizeSum, firstPlaces, secondPlaces,
thirdPlaces, photo {...}``

Driver and trainer paths are best-guessed (``best/drivers``,
``best/trainers``). If they 404, override via ``HIPPO_DRIVERS_PATH`` /
``HIPPO_TRAINERS_PATH`` env vars or pass ``path=...`` to the method.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal, Optional

import pandas as pd

from .client import HeppaClient
from .discover import fetch_json


DEFAULT_HORSES_PATH = "/heppa2_backend/statistics/best/horses"
DEFAULT_DRIVERS_PATH = "/heppa2_backend/statistics/best/drivers"
DEFAULT_TRAINERS_PATH = "/heppa2_backend/statistics/best/trainers"

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
    drivers_path: str = os.getenv("HIPPO_DRIVERS_PATH", DEFAULT_DRIVERS_PATH)
    trainers_path: str = os.getenv("HIPPO_TRAINERS_PATH", DEFAULT_TRAINERS_PATH)

    # ------------------------------------------------------------------
    def top_horses(self, discipline: Discipline = "warmblood",
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None,
                   limit: int = 50,
                   only_registered_in_finland: bool = True,
                   path: Optional[str] = None) -> pd.DataFrame:
        params = _build_params(discipline, start_date, end_date, limit,
                               only_registered_in_finland)
        data = fetch_json(self.client, path or self.horses_path, params=params)
        return _normalise_horses(_as_list(data))

    # ------------------------------------------------------------------
    def top_drivers(self, discipline: Discipline = "warmblood",
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None,
                    limit: int = 50,
                    only_registered_in_finland: bool = True,
                    path: Optional[str] = None) -> pd.DataFrame:
        params = _build_params(discipline, start_date, end_date, limit,
                               only_registered_in_finland)
        data = fetch_json(self.client, path or self.drivers_path, params=params)
        return _normalise_people(_as_list(data), subject="driver")

    # ------------------------------------------------------------------
    def top_trainers(self, discipline: Discipline = "warmblood",
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None,
                     limit: int = 50,
                     only_registered_in_finland: bool = True,
                     path: Optional[str] = None) -> pd.DataFrame:
        params = _build_params(discipline, start_date, end_date, limit,
                               only_registered_in_finland)
        data = fetch_json(self.client, path or self.trainers_path, params=params)
        return _normalise_people(_as_list(data), subject="trainer")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_params(discipline: Discipline,
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


def _normalise_people(rows: list[dict], *, subject: str) -> pd.DataFrame:
    """Shared normaliser for drivers and trainers.

    Schema assumption (best-guess, based on consistent Hippos API
    naming): the records look similar to horses but with ``driverId``
    or ``trainerId`` and without species/gender. We try multiple field
    names per column so this works even if the shape differs slightly.
    """
    id_keys = (f"{subject}Id", "id", "personId")
    name_keys = ("name", f"{subject}Name", "fullName")
    out = []
    for i, r in enumerate(rows, start=1):
        starts = _safe_int(r.get("starts"))
        wins = _safe_int(r.get("firstPlaces"))
        seconds = _safe_int(r.get("secondPlaces"))
        thirds = _safe_int(r.get("thirdPlaces"))
        earnings = _safe_int(r.get("prizeSum"))
        out.append({
            "rank": i,
            f"{subject}_id": _first(r, *id_keys),
            subject: _first(r, *name_keys),
            "starts": starts,
            "wins": wins,
            "seconds": seconds,
            "thirds": thirds,
            "win_pct": _pct(wins, starts),
            "place_pct": _pct((wins or 0) + (seconds or 0) + (thirds or 0), starts),
            "earnings_eur": earnings,
        })
    return pd.DataFrame(out)


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


def _pct(num: Optional[int], denom: Optional[int]) -> Optional[float]:
    if not denom or num is None:
        return None
    return round(100.0 * num / denom, 2)
