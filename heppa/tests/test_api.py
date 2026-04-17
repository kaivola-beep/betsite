"""Tests for the JSON-based HippoApi using the real response fixture."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from heppa.api import HippoApi, _build_params, _normalise_horses
from heppa.client import HeppaClient


FIX = Path(__file__).parent.parent / "fixtures" / "top_horses_warmblood_2023.json"


def _fixture_horses():
    return json.loads(FIX.read_text(encoding="utf-8"))


def test_build_params_maps_warmblood_to_L():
    p = _build_params("warmblood", "2023-01-01", "2023-12-31", 10, True)
    assert p["species"] == "L"
    assert p["startDate"] == "2023-01-01"
    assert p["endDate"] == "2023-12-31"
    assert p["limit"] == "10"
    assert p["onlyRegisteredInFinland"] == "true"


def test_build_params_maps_coldblood_to_S():
    p = _build_params("coldblood", None, None, 20, False)
    assert p["species"] == "S"
    assert "onlyRegisteredInFinland" not in p
    assert "startDate" not in p


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
