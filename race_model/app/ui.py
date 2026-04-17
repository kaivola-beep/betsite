"""Streamlit UI for race_model.

Launch with::

    streamlit run race_model/app/ui.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Streamlit runs this file as a script, not as a package member, so relative
# imports would fail. Add the repo root to sys.path and use absolute imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import streamlit as st

from race_model.calibration.metrics import reliability_curve, summary_report
from race_model.data.loaders import generate_history, load_starts_from_csv
from race_model.evaluation.backtest import walk_forward
from race_model.evaluation.diagnostics import bucketed_report
from race_model.features import build_features
from race_model.market.compare import edge_table, fair_odds_table
from race_model.models.baseline import PlackettLuceBaseline
from race_model.models.stack import build_stack, build_stack_with_market
from race_model.models.uncertainty import BootstrapUncertainty


st.set_page_config(page_title="Race Model", layout="wide")
st.title("Race-aware probabilistic model")
st.caption(
    "Piste-estimaatin sijaan: kalibroidut voittotodennäköisyydet, "
    "fair odds, epävarmuusarviot ja markkinavertailu. "
    "Validointi aikajärjestyksessä, ei satunnaisella splitillä."
)


# ---------------------------------------------------------------------------
# Sidebar: data + pipeline
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Data")
    source = st.radio("Historia", ["Synteettinen", "CSV"], index=0)
    if source == "Synteettinen":
        n_races = st.slider("Lähtöjä", 80, 600, 250, 10)
        seed = st.number_input("seed", value=42, step=1)
        history_df = generate_history(n_races=int(n_races), seed=int(seed))
    else:
        up = st.file_uploader("history.csv", type=["csv"])
        if up is None:
            st.stop()
        tmp = Path("/tmp/race_history.csv")
        tmp.write_bytes(up.getvalue())
        history_df = load_starts_from_csv(tmp)

    st.header("Pipeline")
    use_market = st.checkbox("Käytä markkinadataa (with_market)", value=False)
    calibration_method = st.selectbox(
        "Kalibrointi", ["temperature", "isotonic", "temperature+isotonic", "none"],
        index=0,
    )
    n_bootstrap = st.slider("Bootstrap-draws", 0, 60, 20, 5)


@st.cache_data(show_spinner=False)
def _train_cached(history_df: pd.DataFrame, use_market: bool, calib: str):
    from race_model.models.stack import build_stack, build_stack_with_market
    stack = (build_stack_with_market(history_df, calibration=calib)
             if use_market else build_stack(history_df, calibration=calib))
    return stack


stack = _train_cached(history_df, use_market, calibration_method)

tab_race, tab_eval, tab_drift = st.tabs([
    "Lähdön ennuste",
    "Kalibrointi & backtest",
    "Bucket-raportit",
])


with tab_race:
    races = sorted(history_df["race_id"].unique())
    rid = st.selectbox("Valitse lähtö", races, index=len(races) - 1)
    card = history_df[history_df["race_id"] == rid].copy()
    # Hide the outcome so the user sees the prediction as if the race were live
    display_card = card.drop(columns=["finished_position"], errors="ignore")
    pred = stack.predict(display_card)

    # Uncertainty via baseline bootstrap
    if n_bootstrap > 0:
        bs = BootstrapUncertainty(
            factory=lambda: PlackettLuceBaseline(feature_cols=stack.feature_cols),
            n=int(n_bootstrap), prob_col="p_baseline",
        )
        bs.fit(build_features(history_df))
        draws = bs.predict_draws(build_features(display_card))
        summary = bs.summarise(draws, display_card)
        pred = pred.merge(summary[["race_id", "program_number",
                                     "p_sd", "p_p05", "p_p95"]],
                          on=["race_id", "program_number"], how="left")

    pred = fair_odds_table(pred)
    if "market_share" in card.columns:
        pred = edge_table(pred, card)

    pred = pred.sort_values("p_ens", ascending=False)
    show_cols = ["program_number", "horse_id", "p_baseline", "p_boosted", "p_ens",
                 "fair_odds", "p_sd", "p_p05", "p_p95", "p_market_implied", "edge"]
    show_cols = [c for c in show_cols if c in pred.columns]
    fmt = {c: "{:.3%}" for c in ("p_baseline", "p_boosted", "p_ens", "p_sd",
                                   "p_p05", "p_p95", "p_market_implied")}
    fmt.update({"fair_odds": "{:.2f}", "edge": "{:.2f}"})
    st.dataframe(pred[show_cols].style.format(fmt), use_container_width=True)

    st.caption("Kalibrointikerros: " + calibration_method +
               "  |  Markkinadata: " + ("kyllä" if use_market else "ei"))


with tab_eval:
    st.subheader("Walk-forward backtest")
    k = st.slider("Foldien määrä", 2, 8, 4)
    if st.button("Aja backtest"):
        def builder(train_df):
            return (build_stack_with_market(train_df, calibration=calibration_method)
                    if use_market
                    else build_stack(train_df, calibration=calibration_method))
        with st.spinner("Running walk-forward evaluation..."):
            res = walk_forward(history_df, builder, k_folds=int(k))
        st.dataframe(res.summary(), use_container_width=True)
        st.json(res.stability())

        p = res.oof_probs["p_ens"].to_numpy()
        y = (res.oof_probs["finished_position"] == 1).astype(int).to_numpy()
        rep = summary_report(p, y)
        st.metric("OOF log-loss", f"{rep.log_loss:.4f}")
        st.metric("OOF Brier", f"{rep.brier:.4f}")
        st.metric("OOF ECE", f"{rep.ece:.4f}")

        rc = reliability_curve(p, y, n_bins=10)
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=rc["p_mean"], y=rc["y_mean"], mode="lines+markers",
                                  name="observed"))
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines",
                                  name="perfect", line=dict(dash="dash")))
        fig.update_layout(title="Reliability curve",
                          xaxis_title="Predicted probability",
                          yaxis_title="Observed frequency")
        st.plotly_chart(fig, use_container_width=True)
        st.session_state["oof"] = res.oof_probs


with tab_drift:
    oof = st.session_state.get("oof")
    if oof is None:
        st.info("Aja ensin backtest 'Kalibrointi & backtest' -välilehdessä.")
    else:
        for label, t in bucketed_report(oof).items():
            st.subheader(label)
            st.dataframe(t, use_container_width=True)
