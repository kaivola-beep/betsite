"""Tests for travsport race_stats parser with real fixture."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from travsport.api import (
    RaceStats,
    TravsportApi,
    make_race_id,
    parse_dotnet_date,
    parse_km_time,
)
from travsport.client import TravsportClient


FIX = Path(__file__).parent.parent / "fixtures" / "race_stats_sample.json"


def _load():
    return json.loads(FIX.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_make_race_id():
    assert make_race_id("2026-04-17", 18, 1) == "2026-04-17_18_1"
    assert make_race_id("2026-04-17", "18", "3") == "2026-04-17_18_3"


def test_parse_dotnet_date_roundtrips_ms():
    d = parse_dotnet_date("/Date(1690848000000)/")
    assert d is not None
    assert d.tzinfo is not None
    # 1690848000 seconds = 2023-08-01 UTC
    assert d == datetime(2023, 8, 1, tzinfo=timezone.utc)


def test_parse_km_time_swedish_format():
    assert parse_km_time("22,4") == pytest.approx(82.4)   # 1:22.4 per km
    assert parse_km_time("20,0") == pytest.approx(80.0)
    assert parse_km_time("31,4") == pytest.approx(91.4)
    assert parse_km_time("-") is None
    assert parse_km_time("‒") is None


# ---------------------------------------------------------------------------
# RaceStats
# ---------------------------------------------------------------------------

def test_race_stats_from_json_parses_past_performances():
    stats = RaceStats.from_json("2026-04-17_18_1", _load())
    pp = stats.past_performances
    assert len(pp) == 7   # 5 for horse 6 + 2 for horse 7
    assert set(pp["program_number"]) == {6, 7}
    # Horse 6 has one "V"-type race that placed 6 at 21.9s odds 77.15
    row = pp[(pp["program_number"] == 6) & (pp["placing"] == 6)].iloc[0]
    assert row["km_time_s"] == pytest.approx(81.9)
    assert row["win_odds"] == pytest.approx(77.15)
    assert bool(row["is_competition"]) is True


def test_race_stats_horse_summary_has_life_and_last_year():
    stats = RaceStats.from_json("2026-04-17_18_1", _load())
    sm = stats.horse_summary.set_index("program_number")
    assert int(sm.loc[6, "life_starts"]) == 2
    assert sm.loc[6, "life_earnings_sek"] == pytest.approx(7000.0)
    assert sm.loc[7, "last_year"] == "2025"
    assert int(sm.loc[7, "last_year_starts"]) == 2


def test_race_stats_filters_qualifiers_from_feature_frame():
    stats = RaceStats.from_json("2026-04-17_18_1", _load())
    feats = stats.to_race_model_features(last_n=5,
                                           reference_date="2026-04-17")
    # Horse 6 has only 2 "V" competition rows (1 DNF with place 0, 1 placed 6)
    f6 = feats[feats["program_number"] == 6].iloc[0]
    assert len(f6["prior_finishes"]) == 2
    assert 6 in f6["prior_finishes"]
    assert 0 in f6["prior_finishes"]


def test_api_race_stats_calls_correct_endpoint():
    client = TravsportClient()
    api = TravsportApi(client=client)
    with patch.object(client, "get_json",
                       return_value=_load()) as mock_get:
        stats = api.race_stats("2026-04-17_18_1")
    args, _ = mock_get.call_args
    assert args[0] == "/services/race/2026-04-17_18_1/stats"
    assert not stats.past_performances.empty
