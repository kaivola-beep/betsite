"""Streamlit UI for the Toto Optimizer.

Launch with::

    streamlit run toto_optimizer/app/ui.py
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from ..data.loaders import (
    generate_demo_card,
    load_pool_shares_from_csv,
    load_race_card_from_csv,
    load_race_card_from_json,
    race_card_to_dataframe,
)
from ..data.schemas import RaceCard
from ..features.engineering import build_features
from ..models.ensemble import LogLinearEnsemble
from ..models.predict import PlackettLuceModel, ensure_prob_normalised
from ..optimizer.objective_functions import ObjectiveContext
from ..optimizer.tickets import GenerationConfig, generate_tickets
from ..pool.market_model import MarketModel
from ..simulation.monte_carlo import SimulationConfig, simulate


st.set_page_config(page_title="Toto Optimizer", layout="wide")
st.title("Toto Optimizer")
st.caption(
    "Kalibroi hevoskohtaiset voittotodennäköisyydet, vertaa niitä Veikkauksen "
    "peliprosentteihin ja generoi edullisia pelirivejä. Kaikki luvut ovat "
    "mallin arvioita - voittoja ei luvata."
)

# ---------------------------------------------------------------------------
# Sidebar: data + product config
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Data")
    source = st.radio("Datalähde", ["Demo", "CSV", "JSON"], index=0)

    card: RaceCard | None = None
    extra_shares = None

    product = st.selectbox("Pelimuoto", ["toto4", "toto5", "toto64", "toto75", "toto76"], index=3)
    jackpot = st.number_input("Jackpot (EUR)", min_value=0.0, value=250_000.0, step=10_000.0)
    pool_eur = st.number_input("Pool / kierroksen koko (EUR)", min_value=0.0, value=500_000.0, step=10_000.0)
    takeout = st.slider("Takeout", 0.0, 0.5, 0.25, 0.01)

    if source == "Demo":
        n_races = st.slider("Lähtöjä", 3, 8, 7)
        seed = st.number_input("Seed", value=42, step=1)
        card = generate_demo_card(product=product, n_races=int(n_races),
                                   jackpot=jackpot, total_pool=pool_eur, seed=int(seed))
    elif source == "CSV":
        up = st.file_uploader("Kilpailu-CSV (long format)", type=["csv", "tsv"])
        if up is not None:
            tmp = Path("/tmp/toto_upload.csv")
            tmp.write_bytes(up.getvalue())
            card = load_race_card_from_csv(tmp, product=product, jackpot=jackpot,
                                              total_pool=pool_eur, takeout=takeout)
        pool_up = st.file_uploader("Poolijakauma-CSV (valinnainen)", type=["csv"])
        if pool_up is not None:
            tmp = Path("/tmp/toto_pool.csv")
            tmp.write_bytes(pool_up.getvalue())
            extra_shares = load_pool_shares_from_csv(tmp)
    else:
        up = st.file_uploader("Kilpailu-JSON", type=["json"])
        if up is not None:
            tmp = Path("/tmp/toto_upload.json")
            tmp.write_bytes(up.getvalue())
            card = load_race_card_from_json(tmp)

    st.header("Strategia")
    strategy = st.selectbox("Strategia", ["max_ev", "jackpot", "max_hit"], index=1)
    budget = st.number_input("Budjetti (EUR)", min_value=1.0, value=20.0, step=1.0)
    stake_unit = st.number_input("Rivin hinta (EUR)", min_value=0.05, value=0.10, step=0.05)
    jackpot_gamma = st.slider("Jackpot-paino (gamma)", 0.0, 2.0, 0.5, 0.05)
    top_k = st.slider("Top-N hevosta per lähtö", 3, 10, 6)
    max_per_leg = st.slider("Maks. hevosta per lähtö systeemissä", 1, 6, 3)

    st.header("Malli")
    w_model = st.slider("Malli-paino", 0.0, 1.0, 0.6, 0.05)
    w_market = 1.0 - w_model
    st.caption(f"Markkina-paino = {w_market:.2f}")

if card is None:
    st.info("Valitse datalähde sivupaneelista tai käytä Demo-dataa.")
    st.stop()


# ---------------------------------------------------------------------------
# Build probabilities
# ---------------------------------------------------------------------------

long_df = race_card_to_dataframe(card)
feats = build_features(long_df)
pl = PlackettLuceModel()
model_probs = pl.predict_probabilities(feats)
model_probs = ensure_prob_normalised(model_probs)

debias = st.sidebar.selectbox(
    "Pool-shares -> probability debias",
    ["none", "power", "shin"],
    index=0,
    help=(
        "Raakaosuudet (none) on turvallinen oletus. 'power' (alpha<1) pehmentää "
        "suosikkeja; kalibroi aina dataan. 'shin' on kiinteiden kertoimien "
        "menetelma, ei täysin oikea pari-mutueliin - mukana vertailun vuoksi."
    ),
)
power_alpha = st.sidebar.slider("power alpha", 0.70, 1.20, 0.90, 0.01,
                                 disabled=(debias != "power"))
market = MarketModel(method=debias, power_alpha=float(power_alpha))
market_probs = market.annotate_card(card, extra_shares=extra_shares)

ensemble = LogLinearEnsemble(w_model=w_model, w_market=1 - w_model)
blended = ensemble.blend(model_probs, market_probs)

# Keep a clean table for display
disp = blended.merge(market_probs, on=["race_id", "program_number"], how="left")
disp["fair_odds"] = 1.0 / np.clip(disp["prob_ens"], 1e-9, 1.0)
disp["edge"] = disp["prob_ens"] / np.clip(disp["p_market"], 1e-9, 1.0)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_overview, tab_tickets, tab_sim, tab_data = st.tabs([
    "Todennäköisyydet & edge",
    "Pelirivit",
    "Simulaatio",
    "Raakadata",
])

with tab_overview:
    for race in card.races:
        st.subheader(f"Lähtö {race.race_number}: {race.track} {race.distance_m}m ({race.start_type.value})")
        g = disp[disp.race_id == race.race_id].copy()
        g = g.sort_values("prob_ens", ascending=False)
        g = g.rename(columns={
            "prob_ens": "P(voitto)",
            "p_market": "P(market, Shin)",
            "pool_share": "pool-osuus",
        })
        show_cols = ["program_number", "P(voitto)", "P(market, Shin)", "pool-osuus", "fair_odds", "edge"]
        st.dataframe(g[show_cols].style.format({
            "P(voitto)": "{:.3%}",
            "P(market, Shin)": "{:.3%}",
            "pool-osuus": "{:.3%}",
            "fair_odds": "{:.2f}",
            "edge": "{:.2f}",
        }), use_container_width=True)


with tab_tickets:
    p_leg: list[dict[int, float]] = []
    s_leg: list[dict[int, float]] = []
    for race in card.races:
        gm = blended[blended.race_id == race.race_id]
        p_leg.append(dict(zip(gm.program_number, gm.prob_ens)))
        gs = market_probs[market_probs.race_id == race.race_id]
        s_leg.append(dict(zip(gs.program_number, gs.pool_share)))

    n_other = max(int(pool_eur / max(stake_unit, 0.05)), 1000) if pool_eur > 0 else 20_000
    ctx = ObjectiveContext(
        p_leg=p_leg, s_leg=s_leg, takeout=takeout,
        pool_eur=pool_eur, jackpot_eur=jackpot, n_other_tickets=n_other,
        stake_unit=stake_unit,
    )
    cfg = GenerationConfig(strategy=strategy, budget_eur=float(budget),
                            stake_unit=float(stake_unit), jackpot_gamma=float(jackpot_gamma),
                            top_k_per_leg=int(top_k), max_per_leg_in_system=int(max_per_leg))
    tickets = generate_tickets(ctx, cfg)

    if not tickets:
        st.warning("Ei löytynyt rivejä nykyisillä asetuksilla. Löysennä suodattimia.")
    else:
        rows = []
        for i, t in enumerate(tickets, 1):
            rows.append({
                "#": i,
                "stake": t.stake,
                "hit_prob": t.hit_probability,
                "EV": t.expected_value,
                "uniqueness": t.uniqueness,
                "selections": " | ".join("[" + ",".join(map(str, s)) + "]" for s in t.selections),
                "rationale": t.rationale,
            })
        dfT = pd.DataFrame(rows)
        st.dataframe(dfT.style.format({
            "stake": "{:.2f}",
            "hit_prob": "{:.3%}",
            "EV": "{:+.2f}",
            "uniqueness": "{:.3f}",
        }), use_container_width=True)

        total_stake = sum(t.stake for t in tickets)
        total_ev = sum(t.expected_value for t in tickets)
        hit_any = 1 - np.prod([1 - t.hit_probability for t in tickets])
        c1, c2, c3 = st.columns(3)
        c1.metric("Rivien lkm", len(tickets))
        c2.metric("Panos yht.", f"{total_stake:.2f} €")
        c3.metric("Yhteis-EV", f"{total_ev:+.2f} €")
        st.caption(f"Hit any = {hit_any:.2%}")

        # Download
        st.download_button("Lataa rivit JSON:ina",
                           data=json.dumps([t.model_dump() for t in tickets], indent=2, default=str),
                           file_name="tickets.json",
                           mime="application/json")
        st.session_state["tickets"] = tickets
        st.session_state["ctx"] = ctx


with tab_sim:
    tickets = st.session_state.get("tickets", [])
    ctx = st.session_state.get("ctx", None)
    if not tickets or ctx is None:
        st.info("Generoi ensin rivejä 'Pelirivit'-välilehdessä.")
    else:
        n_sims = st.slider("Simulaatioita", 500, 20_000, 2000, 500)
        sim = simulate(tickets, ctx, SimulationConfig(n_sims=int(n_sims), seed=42))
        st.subheader("Portfolio")
        st.json(sim.portfolio)
        st.subheader("Rivi-kohtaiset tulokset")
        st.dataframe(pd.DataFrame(sim.ticket_summaries), use_container_width=True)
        if len(sim.per_sim_profit) > 0:
            import plotly.express as px
            fig = px.histogram(sim.per_sim_profit, nbins=60,
                                title="Nettotulos per simulaatio (EUR)")
            st.plotly_chart(fig, use_container_width=True)


with tab_data:
    st.dataframe(long_df, use_container_width=True)
