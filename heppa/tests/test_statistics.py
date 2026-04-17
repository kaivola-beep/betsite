"""Parser tests against fixture HTML snapshots."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from heppa.client import HeppaClient
from heppa.statistics import HeppaStatistics, parse_table_html


FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_top_horses_columns_and_rows():
    df = parse_table_html(_load("top_horses_sample.html"))
    assert list(df.columns)[:4] == ["rank", "name", "starts", "wins"]
    assert len(df) == 4
    assert df.iloc[0]["name"] == "Tähtivalo"
    assert int(df.iloc[0]["starts"]) == 18
    assert int(df.iloc[0]["wins"]) == 7
    assert df.iloc[0]["earnings"] == pytest.approx(45200.0, abs=1e-6)
    assert df.iloc[0]["win_pct"] == pytest.approx(38.9, abs=1e-6)


def test_parse_top_drivers_maps_finnish_headers():
    df = parse_table_html(_load("top_drivers_sample.html"),
                           subject_key="driver")
    assert "driver" in df.columns
    assert df.iloc[0]["driver"] == "Virtanen V."
    assert int(df.iloc[0]["starts"]) == 220
    assert df.iloc[0]["earnings"] == pytest.approx(612300.0)


def test_statistics_wrapper_passes_params():
    client = HeppaClient()
    stats = HeppaStatistics(client=client)
    with patch.object(client, "get_html",
                       return_value=_load("top_horses_sample.html")) as mock:
        df = stats.top_horses(discipline="warmblood",
                               start_date="2023-01-01", end_date="2023-12-31")
    args, kwargs = mock.call_args
    assert args[0] == "/mobiili/statistics/horses/top/warmblood"
    assert kwargs["params"] == {"startDate": "2023-01-01",
                                 "endDate": "2023-12-31",
                                 "monte": "x"}
    assert len(df) == 4


def test_parse_handles_missing_rank_column():
    html = """
    <table><thead><tr><th>Nimi</th><th>Startit</th><th>V</th></tr></thead>
    <tbody><tr><td>Foo</td><td>10</td><td>3</td></tr></tbody></table>
    """
    df = parse_table_html(html)
    assert "rank" in df.columns
    assert df.iloc[0]["rank"] == 1


def test_parse_surfaces_unmapped_columns():
    html = """
    <table><thead><tr>
      <th>Nimi</th><th>Startit</th><th>UnknownColX</th>
    </tr></thead>
    <tbody><tr><td>X</td><td>5</td><td>foo</td></tr></tbody></table>
    """
    df = parse_table_html(html)
    assert "UnknownColX" in df.attrs["unmapped"]
