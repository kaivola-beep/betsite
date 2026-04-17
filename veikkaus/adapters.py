"""Map Veikkaus Toto-info JSON to the project's own schemas.

The JSON field names on the Veikkaus API are stable enough for
production use, but they are *not* fully documented publicly. We use
best-effort name resolution with fallbacks — every field is resolved
through :func:`_first_key` which tries multiple candidate keys. That
makes the mapping robust to minor API changes and to Finnish/English
field-name variation.

Two public functions are offered:

* :func:`to_toto_optimizer_card` – returns a
  :class:`toto_optimizer.data.schemas.RaceCard` + a list of
  :class:`~toto_optimizer.data.schemas.PoolShare` overrides so the
  downstream optimizer can use them directly.
* :func:`to_race_model_starts` – returns a long-format DataFrame
  matching :mod:`race_model.data.loaders`' CSV schema (without
  ``finished_position``, i.e. for prediction rather than training).

Both functions take a :class:`TotoInfo` instance and a ``card_id`` and
do the required ``pool -> race -> runner -> odds`` joins.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Iterable, Optional

import pandas as pd

from .toto import TotoInfo


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_key(d: dict, *names: str, default=None):
    """Return ``d[first_name_that_exists]`` or ``default``."""
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    return default


def _race_id(race: dict) -> str:
    return str(_first_key(race, "id", "raceId", "race_id"))


def _card_id(card: dict) -> str:
    return str(_first_key(card, "cardId", "id", "card_id"))


def _program_number(runner: dict) -> int:
    return int(_first_key(runner, "startNumber", "programNumber",
                           "number", default=0))


def _horse_id(runner: dict) -> str:
    # Prefer a stable runner id; fall back to horse name if missing.
    return str(_first_key(runner, "runnerId", "horseId", "id",
                           _first_key(runner, "horseName", "name")))


def _pool_type(pool: dict) -> str:
    return str(_first_key(pool, "poolType", "type", default="")).upper()


def _start_type(race: dict) -> str:
    t = str(_first_key(race, "startType", "start_type", default="volt")).lower()
    if t in ("v", "volt"):
        return "volt"
    if t in ("a", "auto", "automated", "autostart"):
        return "auto"
    return t or "volt"


def _parse_pool_share(entry: dict) -> Optional[float]:
    """Return pool share as a fraction in [0, 1], regardless of unit."""
    for key in ("stakePct", "stakePercent", "betPct", "percent",
                "stakeFraction", "share"):
        if key in entry and entry[key] is not None:
            val = float(entry[key])
            return val / 100.0 if val > 1.0 else val
    # Try deriving from odds if no share is given (1/odds, normalised later)
    for key in ("odds", "decimalOdds", "currentOdds"):
        if key in entry and entry[key]:
            try:
                o = float(entry[key])
                if o > 1.0:
                    return 1.0 / o
            except (TypeError, ValueError):
                pass
    return None


# ---------------------------------------------------------------------------
# Adapter 1: race_model long-format DataFrame
# ---------------------------------------------------------------------------

def to_race_model_starts(info: TotoInfo, card_id: str | int,
                          *, include_market: bool = True) -> pd.DataFrame:
    """Return a DataFrame compatible with :mod:`race_model.data.loaders`.

    Columns populated:
    ``race_id, race_date, track, distance_m, start_type, program_number,
    horse_id, driver_id, trainer_id, post_position, market_share,
    published_odds``.

    Recent-form arrays (``prior_finishes`` etc.) are **not** populated
    here — that data lives in a separate Veikkaus feed not exposed by
    the public Toto-info endpoints. For live race scoring you should
    enrich this DataFrame with historical data from your own store
    (see :mod:`race_model.models.uncertainty` and
    :func:`race_model.data.loaders.load_starts_from_csv`).
    """
    pools = info.card_pools(card_id)
    race_ids = _races_from_pools(pools)
    card_meta = _find_card_meta(info, card_id)

    win_pool_by_race = _win_pool_by_race(pools) if include_market else {}

    rows: list[dict] = []
    for race_id in race_ids:
        runners = info.race_runners(race_id)
        race_meta = _extract_race_meta(runners, card_meta)

        shares_map: dict[int, dict[str, Optional[float]]] = {}
        if include_market:
            pool_id = win_pool_by_race.get(race_id)
            if pool_id is not None:
                try:
                    odds_json = info.pool_odds(pool_id)
                    shares_map = _extract_win_shares(odds_json)
                except Exception as e:
                    log.warning("pool_odds(%s) failed: %s", pool_id, e)

        for r in runners:
            pn = _program_number(r)
            share_info = shares_map.get(pn, {})
            rows.append({
                "race_id": str(race_id),
                "race_date": race_meta["race_date"],
                "track": race_meta["track"],
                "distance_m": race_meta["distance_m"],
                "start_type": race_meta["start_type"],
                "race_class": race_meta.get("race_class"),
                "track_condition": race_meta.get("track_condition"),
                "program_number": pn,
                "horse_id": _horse_id(r),
                "driver_id": _first_key(r, "driverName", "driver", "kuski"),
                "trainer_id": _first_key(r, "trainerName", "trainer", "valmentaja"),
                "post_position": int(_first_key(r, "postPosition",
                                                  "startNumber", default=pn) or pn),
                "carried_weight_kg": _first_key(r, "weight", "carriedWeight",
                                                  default=None),
                "prior_finishes": [],
                "prior_km_times": [],
                "prior_earnings": [],
                "prior_opponent_strengths": [],
                "days_since_last_start": _first_key(r, "daysSinceLastStart",
                                                     default=None),
                "gallop_risk": None,
                "speed_rating": _first_key(r, "speedRating",
                                             "ratingSpeed", default=None),
                "class_rating": _first_key(r, "classRating",
                                             "ratingClass", default=None),
                "stamina_rating": _first_key(r, "staminaRating",
                                               "ratingStamina", default=None),
                "equipment_change": _first_key(r, "equipmentChanged",
                                                 default=False),
                "shoeing_change": _first_key(r, "shoeingChanged",
                                               default=False),
                "market_share": share_info.get("share"),
                "published_odds": share_info.get("odds"),
            })

    df = pd.DataFrame(rows)
    # race_date must be a ``datetime.date``
    df["race_date"] = df["race_date"].apply(_coerce_date)
    return df


# ---------------------------------------------------------------------------
# Adapter 2: toto_optimizer RaceCard
# ---------------------------------------------------------------------------

def to_toto_optimizer_card(info: TotoInfo, card_id: str | int,
                            *, product: str = "toto75"):
    """Return a :class:`toto_optimizer.data.schemas.RaceCard` and a list
    of :class:`~toto_optimizer.data.schemas.PoolShare` overrides.

    ``product`` picks which combination pool (T75, T76, T65, T5, T4) is
    used to infer ``total_pool`` and ``jackpot`` when those values are
    exposed.
    """
    from toto_optimizer.data.schemas import (  # imported lazily
        Horse, PoolShare, Race, RaceCard, StartType,
    )
    pools = info.card_pools(card_id)
    race_ids = _races_from_pools(pools)
    card_meta = _find_card_meta(info, card_id)
    win_pool_by_race = _win_pool_by_race(pools)
    combo_pool = _find_combo_pool(pools, product)

    races: list[Race] = []
    extra_shares: list[PoolShare] = []
    for race_id in race_ids:
        runners = info.race_runners(race_id)
        race_meta = _extract_race_meta(runners, card_meta)

        shares_map: dict[int, dict[str, Optional[float]]] = {}
        win_pool_id = win_pool_by_race.get(race_id)
        if win_pool_id is not None:
            try:
                shares_map = _extract_win_shares(info.pool_odds(win_pool_id))
            except Exception as e:
                log.warning("pool_odds(%s) failed: %s", win_pool_id, e)

        horses: list[Horse] = []
        for r in runners:
            pn = _program_number(r)
            share_info = shares_map.get(pn, {})
            horses.append(Horse(
                program_number=pn,
                name=str(_first_key(r, "horseName", "name", default=f"#{pn}")),
                driver=_first_key(r, "driverName", "driver"),
                trainer=_first_key(r, "trainerName", "trainer"),
                post_position=int(_first_key(r, "postPosition", default=pn) or pn),
                speed_rating=_first_key(r, "speedRating", default=None),
                class_rating=_first_key(r, "classRating", default=None),
                stamina_rating=_first_key(r, "staminaRating", default=None),
                pool_percentage=(share_info["share"] * 100.0)
                if share_info.get("share") is not None else None,
                published_odds=share_info.get("odds"),
            ))
            share = share_info.get("share")
            if share is not None:
                extra_shares.append(PoolShare(race_id=str(race_id),
                                                program_number=pn,
                                                share=float(share)))

        races.append(Race(
            race_id=str(race_id),
            race_number=int(_first_key(runners[0] if runners else {},
                                         "raceNumber", default=len(races) + 1)),
            track=str(race_meta["track"] or ""),
            distance_m=int(race_meta["distance_m"] or 2100),
            start_type=StartType(race_meta["start_type"]),
            race_class=race_meta.get("race_class"),
            horses=horses,
        ))

    card_payload = RaceCard(
        product=product,
        date=str(card_meta.get("card_date") or date.today()),
        venue=str(card_meta.get("venue", "")),
        races=races,
        jackpot=float(_first_key(combo_pool or {}, "jackpot", "carryOver",
                                    default=0.0) or 0.0),
        total_pool=float(_first_key(combo_pool or {}, "expectedPool",
                                       "currentPool", default=0.0) or 0.0),
        takeout=None,
    )
    return card_payload, extra_shares


# ---------------------------------------------------------------------------
# Small private helpers
# ---------------------------------------------------------------------------

def _coerce_date(v) -> date:
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            pass
    return date.today()


def _races_from_pools(pools: Iterable[dict]) -> list[str]:
    """Return the ordered list of race ids appearing in the pool list."""
    seen: list[str] = []
    for p in pools:
        ids = _first_key(p, "raceIds", "races", default=[])
        if isinstance(ids, list):
            for rid in ids:
                s = str(rid)
                if s not in seen:
                    seen.append(s)
        elif ids is not None:
            s = str(ids)
            if s not in seen:
                seen.append(s)
    return seen


def _find_card_meta(info: TotoInfo, card_id: str | int) -> dict:
    """Look up basic metadata (venue, date) for a card from /cards/today."""
    try:
        for c in info.cards_today():
            if str(_card_id(c)) == str(card_id):
                return {
                    "venue": _first_key(c, "trackName", "track", "venue"),
                    "card_date": _first_key(c, "meetDate", "date", "cardDate"),
                }
    except Exception as e:
        log.warning("cards_today() failed: %s", e)
    return {}


def _extract_race_meta(runners: list[dict], card_meta: dict) -> dict:
    """Infer race-level metadata from a single runner record (the API
    often repeats the race fields on every runner)."""
    if not runners:
        return {"track": card_meta.get("venue"), "distance_m": 2100,
                "start_type": "volt", "race_date": card_meta.get("card_date")}
    r0 = runners[0]
    return {
        "track": _first_key(r0, "trackName", "track", card_meta.get("venue")),
        "distance_m": _first_key(r0, "distance", "distanceMeters", default=2100),
        "start_type": _start_type(r0),
        "race_class": _first_key(r0, "raceClass", "className"),
        "track_condition": _first_key(r0, "trackCondition", "surface"),
        "race_date": _first_key(r0, "startTime", card_meta.get("card_date")),
    }


def _win_pool_by_race(pools: Iterable[dict]) -> dict[str, str]:
    """Return a ``race_id -> win_pool_id`` mapping."""
    out: dict[str, str] = {}
    for p in pools:
        if _pool_type(p) == "WIN":
            ids = _first_key(p, "raceIds", "races", default=[])
            if isinstance(ids, list) and ids:
                out[str(ids[0])] = str(_first_key(p, "id", "poolId"))
            elif ids:
                out[str(ids)] = str(_first_key(p, "id", "poolId"))
    return out


def _find_combo_pool(pools: Iterable[dict], product: str) -> Optional[dict]:
    want = product.upper().replace("TOTO", "T")  # "toto75" -> "T75"
    for p in pools:
        if _pool_type(p) == want:
            return p
    return None


def _extract_win_shares(odds_json: Any) -> dict[int, dict[str, Optional[float]]]:
    """Return ``{program_number: {"share": float, "odds": float}}``.

    The Veikkaus win-pool endpoint returns a list of per-runner entries;
    different versions nest this under various keys. We normalise by
    trying common locations.
    """
    if isinstance(odds_json, dict):
        items = (odds_json.get("runners")
                 or odds_json.get("entries")
                 or odds_json.get("odds")
                 or odds_json.get("collection")
                 or [])
    else:
        items = odds_json or []

    out: dict[int, dict[str, Optional[float]]] = {}
    for e in items:
        if not isinstance(e, dict):
            continue
        pn = int(_first_key(e, "startNumber", "programNumber",
                             "number", default=0) or 0)
        if pn <= 0:
            continue
        odds_val = _first_key(e, "odds", "decimalOdds", "currentOdds", default=None)
        out[pn] = {
            "share": _parse_pool_share(e),
            "odds": float(odds_val) if odds_val else None,
        }
    return out
