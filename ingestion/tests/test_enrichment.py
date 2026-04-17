"""Tests for the enrichment layer using mocked Heppa/Veikkaus clients."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from ingestion.enrichment import (
    enrich_with_history,
    load_horse_map,
    resolve_hippo_ids,
)


def _minimal_card():
    return pd.DataFrame([
        {"race_id": "R1", "program_number": 1, "horse_id": "V-001",
         "horse_name": "Alpha", "market_share": 0.4,
         "hippoHorseId": "HIP-1", "prior_finishes": [],
         "prior_km_times": [], "prior_earnings": [],
         "prior_opponent_strengths": [],
         "days_since_last_start": None, "gallop_risk": None,
         "speed_rating": None, "class_rating": None,
         "stamina_rating": None, "race_date": date(2026, 4, 17)},
        {"race_id": "R1", "program_number": 2, "horse_id": "V-002",
         "horse_name": "Beta", "market_share": 0.6,
         "prior_finishes": [], "prior_km_times": [],
         "prior_earnings": [], "prior_opponent_strengths": [],
         "days_since_last_start": None, "gallop_risk": None,
         "speed_rating": None, "class_rating": None,
         "stamina_rating": None, "race_date": date(2026, 4, 17)},
    ])


def test_resolve_hippo_ids_picks_up_inline_field():
    df = _minimal_card()
    resolved = resolve_hippo_ids(df)
    assert resolved.loc[0, "hippo_horse_id"] == "HIP-1"
    assert pd.isna(resolved.loc[1, "hippo_horse_id"])


def test_resolve_hippo_ids_uses_manual_map(tmp_path):
    map_csv = tmp_path / "map.csv"
    pd.DataFrame([{"horse_name": "Beta", "hippo_horse_id": "HIP-2"}]).to_csv(
        map_csv, index=False)
    horse_map = load_horse_map(map_csv)
    df = _minimal_card()
    resolved = resolve_hippo_ids(df, horse_map=horse_map)
    assert resolved.loc[1, "hippo_horse_id"] == "HIP-2"


def test_enrich_with_history_populates_priors():
    df = resolve_hippo_ids(_minimal_card())
    df.loc[1, "hippo_horse_id"] = "HIP-2"

    api = MagicMock()
    api.horse_starts.side_effect = lambda hid, **kw: pd.DataFrame([{
        "date": pd.Timestamp("2026-04-11"), "placing": 1,
        "km_time_s": 72.0, "earnings_eur": 5000, "win_odds": 3.5,
        "did_run": True, "gallop": False,
    }])
    api.horse_stats.side_effect = Exception("stats unavailable")

    result = enrich_with_history(df, api, last_n=5,
                                   reference_date="2026-04-18",
                                   max_workers=1)
    assert result.resolved == 2
    enriched = result.df
    row0 = enriched.iloc[0]
    assert row0["prior_finishes"] == [1]
    assert row0["prior_km_times"][0] == pytest.approx(72.0)
    assert row0["days_since_last_start"] == 7
    assert row0["gallop_risk"] == 0.0


def test_enrich_with_history_handles_errors_gracefully():
    df = resolve_hippo_ids(_minimal_card())

    api = MagicMock()
    api.horse_starts.side_effect = RuntimeError("boom")

    result = enrich_with_history(df, api, last_n=5, max_workers=1)
    assert len(result.errors) == 1
    # didn't corrupt data
    assert len(result.df) == len(df)
