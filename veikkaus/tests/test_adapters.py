"""Tests for the JSON → schema adapters using fixture payloads."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from veikkaus.adapters import (
    _extract_race_id,
    _extract_win_shares,
    _parse_pool_share,
    _race_number_map,
    _races_from_pools,
    to_race_model_starts,
    to_toto_optimizer_card,
)
from veikkaus.toto import TotoInfo


# ---------------------------------------------------------------------------
# Fixture JSON loosely mirroring what the API returns
# ---------------------------------------------------------------------------

CARD = {"id": "123", "trackName": "Vermo", "date": "2026-04-17"}

POOLS = [
    {"id": "P_WIN_1", "poolType": "WIN", "raceIds": ["R1"]},
    {"id": "P_WIN_2", "poolType": "WIN", "raceIds": ["R2"]},
    {"id": "P_T75", "poolType": "T75", "raceIds": ["R1", "R2"],
     "currentPool": 500000, "jackpot": 250000},
]

RUNNERS_R1 = [
    {"startNumber": 1, "horseName": "Alpha", "driverName": "Driver A",
     "trainerName": "Trainer X", "postPosition": 1, "distance": 2100,
     "startType": "volt", "raceNumber": 1,
     "speedRating": 88, "classRating": 86, "staminaRating": 85},
    {"startNumber": 2, "horseName": "Beta", "driverName": "Driver B",
     "postPosition": 2, "distance": 2100, "startType": "volt",
     "speedRating": 80, "classRating": 78},
]
RUNNERS_R2 = [
    {"startNumber": 1, "horseName": "Gamma", "postPosition": 1,
     "distance": 1609, "startType": "auto", "raceNumber": 2},
    {"startNumber": 2, "horseName": "Delta", "postPosition": 2,
     "distance": 1609, "startType": "auto"},
]

ODDS_R1 = {"runners": [
    {"startNumber": 1, "stakePct": 45.0, "odds": 2.1},
    {"startNumber": 2, "stakePct": 55.0, "odds": 1.75},
]}
ODDS_R2 = {"runners": [
    {"startNumber": 1, "stakePct": 60.0, "odds": 1.6},
    {"startNumber": 2, "stakePct": 40.0, "odds": 2.3},
]}


def _fake_info() -> TotoInfo:
    client = MagicMock()
    info = TotoInfo(client=client)
    info.cards_today = MagicMock(return_value=[CARD])
    info.card_pools = MagicMock(return_value=POOLS)
    info.race_runners = MagicMock(side_effect=lambda rid: RUNNERS_R1
                                    if rid == "R1" else RUNNERS_R2)
    info.pool_odds = MagicMock(side_effect=lambda pid: ODDS_R1
                                if pid == "P_WIN_1" else ODDS_R2)
    return info


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

def test_parse_pool_share_accepts_percent_and_fraction():
    assert _parse_pool_share({"stakePct": 25.5}) == 0.255
    assert _parse_pool_share({"share": 0.3}) == 0.3
    # Fallback to odds
    assert _parse_pool_share({"odds": 4.0}) == 0.25


def test_races_from_pools_collects_unique_ordered():
    ids = _races_from_pools(POOLS)
    assert ids == ["R1", "R2"]


def test_races_from_pools_handles_dict_raceids():
    """Veikkaus sometimes returns raceIds as dicts with raceId + raceNumber."""
    pools = [
        {"id": "P_WIN_1", "poolType": "WIN",
         "raceIds": [{"raceId": 3474965681, "raceNumber": 1}]},
        {"id": "P_T64", "poolType": "T64",
         "raceIds": [
             {"raceId": 3474965681, "raceNumber": 1},
             {"raceId": 3474965682, "raceNumber": 2},
             {"raceId": 3474965683, "raceNumber": 3},
         ]},
    ]
    ids = _races_from_pools(pools)
    assert ids == ["3474965681", "3474965682", "3474965683"]


def test_extract_race_id_from_various_shapes():
    assert _extract_race_id(12345) == "12345"
    assert _extract_race_id("abc") == "abc"
    assert _extract_race_id({"raceId": 999, "raceNumber": 1}) == "999"
    assert _extract_race_id({"id": 42}) == "42"
    assert _extract_race_id(None) == ""
    assert _extract_race_id({"foo": "bar"}) == ""


def test_race_number_map_from_dict_raceids():
    pools = [
        {"poolType": "T64",
         "raceIds": [
             {"raceId": 100, "raceNumber": 3},
             {"raceId": 200, "raceNumber": 4},
         ]},
    ]
    assert _race_number_map(pools) == {"100": 3, "200": 4}


def test_extract_win_shares():
    out = _extract_win_shares(ODDS_R1)
    assert out[1]["share"] == 0.45
    assert out[2]["odds"] == 1.75


# ---------------------------------------------------------------------------
# race_model adapter
# ---------------------------------------------------------------------------

def test_to_race_model_starts_columns_and_rows():
    info = _fake_info()
    df = to_race_model_starts(info, "123")
    assert len(df) == 4
    for c in ("race_id", "race_date", "track", "distance_m", "program_number",
              "horse_id", "market_share", "published_odds"):
        assert c in df.columns
    assert set(df["race_id"]) == {"R1", "R2"}
    assert df["race_date"].iloc[0] == date(2026, 4, 17)
    # Market shares round-trip as fractions
    r1_shares = df[df["race_id"] == "R1"]["market_share"].tolist()
    assert r1_shares == [0.45, 0.55]


def test_to_race_model_starts_no_market():
    info = _fake_info()
    df = to_race_model_starts(info, "123", include_market=False)
    assert df["market_share"].isna().all()


# ---------------------------------------------------------------------------
# toto_optimizer adapter
# ---------------------------------------------------------------------------

def test_to_toto_optimizer_card_basic():
    info = _fake_info()
    card, shares = to_toto_optimizer_card(info, "123", product="toto75")
    assert card.product == "toto75"
    assert card.venue == "Vermo"
    assert len(card.races) == 2
    assert card.total_pool == 500000
    assert card.jackpot == 250000
    # First horse in first race
    h0 = card.races[0].horses[0]
    assert h0.name == "Alpha"
    assert h0.pool_percentage == 45.0
    # Pool-share override list
    assert len(shares) == 4
