"""Tests for horse_stats / horse_starts endpoints and feature extraction."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from heppa.api import (
    HippoApi,
    HorseProfile,
    HorseStats,
    _normalise_horse_starts,
    parse_km_time,
    parse_total_time,
    to_race_model_features,
)
from heppa.client import HeppaClient


FIX_STATS = Path(__file__).parent.parent / "fixtures" / "horse_stats_sample.json"
FIX_STARTS = Path(__file__).parent.parent / "fixtures" / "horse_starts_sample.json"
FIX_PROFILE = Path(__file__).parent.parent / "fixtures" / "horse_profile_sample.json"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# horse_profile
# ---------------------------------------------------------------------------

def test_horse_profile_parses_identity_and_blup():
    prof = HorseProfile.from_json(_load(FIX_PROFILE))
    assert prof.horse_id == "4497501728848759385"
    assert prof.name == "Hide And Seek"
    assert prof.birth_year == 2005
    assert prof.birth_country == "FI"
    assert prof.species == "L"
    assert prof.gender == "R"
    assert prof.dead is True
    assert prof.date_of_death == "2015-06-01"
    assert prof.sire_name == "Express It*"
    assert prof.dam_name == "Smashy Speed"
    assert prof.blup == 121.0
    assert prof.blup_certainty == pytest.approx(0.79)
    assert prof.best_record_s == pytest.approx(73.0)


def test_horse_profile_to_feature_dict_shape():
    prof = HorseProfile.from_json(_load(FIX_PROFILE))
    feats = prof.to_feature_dict()
    for k in ("blup", "blup_certainty", "birth_year", "age", "gender"):
        assert k in feats


def test_api_horse_profile_calls_correct_endpoint():
    client_dummy = type("X", (), {"base_url": "http://x", "timeout_s": 10,
                                    "_session": None, "_throttle": lambda s: None,
                                    "_sleep_backoff": lambda s, a: None,
                                    "cache_dir": None,
                                    "min_request_interval_s": 0})()
    api = HippoApi(client=client_dummy)
    with patch("heppa.api.fetch_json",
                return_value=_load(FIX_PROFILE)) as mock_fetch:
        prof = api.horse_profile("4497501728848759385")
    assert mock_fetch.call_args[0][1] == "/heppa2_backend/horse/4497501728848759385"
    assert prof.name == "Hide And Seek"


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

def test_parse_km_time_long_form():
    assert parse_km_time("1.14.9") == pytest.approx(74.9)
    assert parse_km_time("2.05.0") == pytest.approx(125.0)


def test_parse_km_time_short_form():
    # "14,9" -> 74.9 (implicit 1-minute prefix)
    assert parse_km_time("14,9") == pytest.approx(74.9)
    # "08,3" record-time -> 68.3
    assert parse_km_time("08,3") == pytest.approx(68.3)


def test_parse_km_time_handles_missing():
    assert parse_km_time(None) is None
    assert parse_km_time("") is None
    assert parse_km_time("-") is None


def test_parse_total_time():
    assert parse_total_time("2.40.3") == pytest.approx(160.3)
    assert parse_total_time(None) is None


# ---------------------------------------------------------------------------
# horse_stats
# ---------------------------------------------------------------------------

def test_horse_stats_from_json_parses_total_and_yearly():
    stats = HorseStats.from_json(_load(FIX_STATS))
    assert stats.horse_id == "2180824875766618301"
    assert stats.total["starts"] == 167
    assert stats.total["wins"] == 38
    assert stats.total["car_record_s"] == pytest.approx(68.3)
    assert stats.total["earnings_eur"] == 597086
    # Yearly is a DataFrame
    assert len(stats.yearly) == 4
    yr_2023 = stats.yearly[stats.yearly["year"] == "2023"].iloc[0]
    assert yr_2023["wins"] == 9
    assert yr_2023["earnings_eur"] == 281241


def test_horse_stats_recent_years_ordered():
    stats = HorseStats.from_json(_load(FIX_STATS))
    recent = stats.recent_years(n=2)
    assert list(recent["year"]) == ["2026", "2025"]


def test_api_horse_stats_calls_correct_endpoint():
    client = HeppaClient()
    api = HippoApi(client=client)
    with patch("heppa.api.fetch_json",
                return_value=_load(FIX_STATS)) as mock_fetch:
        stats = api.horse_stats("2180824875766618301")
    assert mock_fetch.call_args[0][1] == "/heppa2_backend/horse/2180824875766618301/stats"
    assert stats.total["starts"] == 167


# ---------------------------------------------------------------------------
# horse_starts
# ---------------------------------------------------------------------------

def test_normalise_horse_starts_basic():
    df = _normalise_horse_starts(_load(FIX_STARTS))
    assert len(df) == 6
    # Upcoming start (placing==0) recognised
    upcoming = df.iloc[0]
    assert upcoming["did_run"] == False
    # Completed start
    done = df.iloc[1]
    assert done["did_run"] == True
    assert done["placing"] == 8
    assert done["km_time_s"] == pytest.approx(71.8)
    assert done["distance_m"] == 1620
    assert done["win_odds"] == pytest.approx(51.38)


def test_normalise_horse_starts_captures_driver_trainer():
    df = _normalise_horse_starts(_load(FIX_STARTS))
    # The gallop=True row (2026-01-24) has driver_id set
    rows = df[df["gallop"] == True]
    assert len(rows) == 1
    assert rows.iloc[0]["driver_name"] == "M Jaara"


def test_api_horse_starts_calls_correct_endpoint():
    client = HeppaClient()
    api = HippoApi(client=client)
    with patch("heppa.api.fetch_json",
                return_value=_load(FIX_STARTS)) as mock_fetch:
        df = api.horse_starts("2180824875766618301", page=1, page_size=10)
    args, kwargs = mock_fetch.call_args
    assert args[1] == "/heppa2_backend/horse/2180824875766618301/starts"
    assert kwargs["params"]["pageNumber"] == "1"
    assert kwargs["params"]["pageSize"] == "10"
    assert len(df) == 6


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def test_to_race_model_features_basic():
    df = _normalise_horse_starts(_load(FIX_STARTS))
    f = to_race_model_features(df, last_n=5, reference_date="2026-04-22")
    # Only completed starts are considered -> 5 taken
    assert len(f["prior_finishes"]) == 5
    # Most-recent first; last completed start was 2026-04-11 with placing=8
    assert f["prior_finishes"][0] == 8
    # km_time of that start: 1.11.8 -> 71.8
    assert f["prior_km_times"][0] == pytest.approx(71.8)
    # gallop_risk: 1 out of 5 completed starts had gallop=True -> 0.2
    assert f["gallop_risk"] == pytest.approx(0.2)
    # days_since_last_start: 2026-04-22 -> 2026-04-11 = 11
    assert f["days_since_last_start"] == 11


def test_to_race_model_features_empty_df():
    f = to_race_model_features(pd.DataFrame())
    assert f["prior_finishes"] == []
    assert f["gallop_risk"] is None
