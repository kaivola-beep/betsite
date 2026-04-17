"""Tests for the JSON-based HippoApi using the real response fixture."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from heppa.api import (
    HippoApi,
    _build_horses_params,
    _build_person_params,
    _normalise_horses,
    _normalise_people_risingshape,
)
from heppa.client import HeppaClient


FIX_HORSES = Path(__file__).parent.parent / "fixtures" / "top_horses_warmblood_2023.json"
FIX_DRIVERS = Path(__file__).parent.parent / "fixtures" / "top_drivers_2026.json"


def _fixture_horses():
    return json.loads(FIX_HORSES.read_text(encoding="utf-8"))


def _fixture_drivers():
    return json.loads(FIX_DRIVERS.read_text(encoding="utf-8"))


def test_build_horses_params_maps_warmblood_to_L():
    p = _build_horses_params("warmblood", "2023-01-01", "2023-12-31", 10, True)
    assert p["species"] == "L"
    assert p["startDate"] == "2023-01-01"
    assert p["endDate"] == "2023-12-31"
    assert p["limit"] == "10"
    assert p["onlyRegisteredInFinland"] == "true"


def test_build_horses_params_maps_coldblood_to_S():
    p = _build_horses_params("coldblood", None, None, 20, False)
    assert p["species"] == "S"
    assert "onlyRegisteredInFinland" not in p
    assert "startDate" not in p


def test_build_person_params_uses_expected_keys():
    p = _build_person_params(track="ALL", limit=30, order="WINS",
                              horse_starts=True, pony_starts=False)
    assert p == {"track": "ALL", "limit": "30", "order": "WINS",
                 "horseStarts": "true", "ponyStarts": "false"}


def test_normalise_horses_returns_expected_columns_and_types():
    df = _normalise_horses(_fixture_horses())
    assert list(df.columns)[:7] == [
        "rank", "horse_id", "name", "species", "gender", "birth_year", "birth_country",
    ]
    assert len(df) == 10
    # First row sanity
    row0 = df.iloc[0]
    assert row0["name"] == "Hierro Boko"
    assert row0["species"] == "L"
    assert row0["gender"] == "gelding"        # "R" -> ruuna -> gelding
    assert row0["birth_year"] == 2014
    assert int(row0["starts"]) == 24
    assert int(row0["wins"]) == 9
    assert int(row0["earnings_eur"]) == 281241
    assert row0["win_pct"] == pytest.approx(37.5)
    # Row with most wins (Mandela Zon: 25/40)
    mandela = df[df["name"] == "Mandela Zon"].iloc[0]
    assert mandela["win_pct"] == pytest.approx(62.5)


def test_normalise_handles_missing_photo_field():
    df = _normalise_horses(_fixture_horses())
    # "God Hyperion" has photoExist=false — row should still be there
    assert "God Hyperion" in df["name"].tolist()


def test_top_horses_calls_correct_endpoint_and_parses():
    client = HeppaClient()
    api = HippoApi(client=client)
    with patch("heppa.api.fetch_json",
                return_value=_fixture_horses()) as mock_fetch:
        df = api.top_horses(discipline="warmblood",
                              start_date="2023-01-01",
                              end_date="2023-12-31",
                              limit=10)
    args, kwargs = mock_fetch.call_args
    # Called with the default horses path
    assert args[1] == "/heppa2_backend/statistics/best/horses"
    assert kwargs["params"]["species"] == "L"
    assert kwargs["params"]["limit"] == "10"
    assert len(df) == 10
    assert df.iloc[0]["name"] == "Hierro Boko"


def test_top_horses_path_override():
    client = HeppaClient()
    api = HippoApi(client=client, horses_path="/custom/path")
    with patch("heppa.api.fetch_json",
                return_value=_fixture_horses()) as mock_fetch:
        api.top_horses()
    assert mock_fetch.call_args[0][1] == "/custom/path"


# ---------------------------------------------------------------------------
# Drivers (risingshape schema)
# ---------------------------------------------------------------------------

def test_normalise_drivers_parses_real_fields():
    df = _normalise_people_risingshape(_fixture_drivers(), subject="driver")
    assert list(df.columns)[:6] == [
        "rank", "driver_id", "driver", "first_name", "last_name", "starts",
    ]
    assert len(df) == 3
    row0 = df.iloc[0]
    assert row0["driver"] == "Raitala Santtu"
    assert row0["first_name"] == "Santtu"
    assert row0["driver_id"] == "282706244229465242"
    assert int(row0["starts"]) == 414
    assert int(row0["wins"]) == 122
    assert int(row0["earnings_eur"]) == 489254
    assert row0["win_pct"] == pytest.approx(29.47)
    assert row0["earnings_per_start"] == pytest.approx(1181.77)
    assert row0["win_odds_per_start"] == pytest.approx(0.85)


def test_top_drivers_calls_templated_path():
    client = HeppaClient()
    api = HippoApi(client=client)
    with patch("heppa.api.fetch_json",
                return_value=_fixture_drivers()) as mock_fetch:
        df = api.top_drivers(start_date="2026-01-01", end_date="2026-12-31",
                               track="ALL", limit=30, order="WINS")
    endpoint = mock_fetch.call_args[0][1]
    assert endpoint == "/heppa2_backend/statistics/risingshape/driver/2026-01-01/2026-12-31"
    params = mock_fetch.call_args[1]["params"]
    assert params["horseStarts"] == "true"
    assert params["ponyStarts"] == "false"
    assert params["order"] == "WINS"
    assert len(df) == 3


def test_top_trainers_uses_trainer_template_by_default():
    client = HeppaClient()
    api = HippoApi(client=client)
    with patch("heppa.api.fetch_json",
                return_value=_fixture_drivers()) as mock_fetch:
        api.top_trainers(start_date="2026-01-01", end_date="2026-12-31")
    endpoint = mock_fetch.call_args[0][1]
    assert endpoint == "/heppa2_backend/statistics/risingshape/trainer/2026-01-01/2026-12-31"


def test_top_drivers_path_override():
    client = HeppaClient()
    api = HippoApi(client=client)
    with patch("heppa.api.fetch_json",
                return_value=_fixture_drivers()) as mock_fetch:
        api.top_drivers(start_date="2026-01-01", end_date="2026-12-31",
                         path="/completely/different")
    assert mock_fetch.call_args[0][1] == "/completely/different"
