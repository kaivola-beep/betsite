"""Market compare + simulation tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from race_model.market.compare import edge_table, fair_odds_table
from race_model.simulation.race_sim import sample_race_winners


def _toy():
    return pd.DataFrame([
        {"race_id": "R1", "program_number": 1, "horse_id": "H1",
         "p_ens": 0.5, "market_share": 0.35},
        {"race_id": "R1", "program_number": 2, "horse_id": "H2",
         "p_ens": 0.3, "market_share": 0.35},
        {"race_id": "R1", "program_number": 3, "horse_id": "H3",
         "p_ens": 0.2, "market_share": 0.30},
    ])


def test_fair_odds_is_reciprocal():
    out = fair_odds_table(_toy())
    assert np.allclose(out["fair_odds"], 1.0 / out["p_ens"])


def test_edge_table_matches_formula():
    df = _toy()
    out = edge_table(df)
    # Expected market-implied prob = share / sum(share)
    expected = np.array([0.35, 0.35, 0.30])
    expected = expected / expected.sum()
    assert np.allclose(out["p_market_implied"], expected, atol=1e-9)
    assert np.allclose(out["edge"], df["p_ens"] / expected, atol=1e-9)


def test_sample_race_winners_sums_to_one():
    df = _toy()
    sim = sample_race_winners(df, n_sims=500, seed=0)
    assert sim["p_simulated"].sum() == pytest.approx(1.0, abs=1e-9)
