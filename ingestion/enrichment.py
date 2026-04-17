"""Fetch a Veikkaus card and enrich every runner with heppa history.

The enrichment step is the critical bridge between the two data sources.
It runs in three phases:

1. **Card fetch.** ``fetch_card_starts(card_id)`` calls the Veikkaus
   adapter to produce the long-format ``race_model`` Starts DataFrame
   with ``market_share``, ``program_number`` etc. filled in.

2. **Horse ID resolution.** Veikkaus runners may or may not carry the
   Hippos ``horseId`` directly. We therefore try three strategies in
   order and record which one hit:

   a) Veikkaus JSON contains ``hippoHorseId`` / ``registryId`` / ...
   b) A pre-built manual mapping CSV ``--horse-map``.
   c) Heppa name search (``/heppa2_backend/horse/search?name=...``) if
      the endpoint is reachable; disabled by default because we don't
      know the exact path yet.

3. **Per-horse history.** For every resolved Hippos horseId we fetch
   the last ``last_n`` starts *and* career stats concurrently (4
   workers by default, matching the Veikkaus robot-guide limits). The
   results are converted to ``race_model`` priors via
   :func:`heppa.api.to_race_model_features`.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from heppa.api import HippoApi, to_race_model_features
from veikkaus.adapters import to_race_model_starts
from veikkaus.toto import TotoInfo

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: fetch Veikkaus card
# ---------------------------------------------------------------------------

def fetch_card_starts(info: TotoInfo, card_id: str | int,
                       include_market: bool = True) -> pd.DataFrame:
    """Return the race_model Starts DataFrame for a Veikkaus card."""
    return to_race_model_starts(info, card_id, include_market=include_market)


# ---------------------------------------------------------------------------
# Step 2: resolve Hippos horseId
# ---------------------------------------------------------------------------

HIPPO_ID_CANDIDATE_COLS = [
    "hippo_horse_id", "hippoHorseId", "horseRegistryId",
    "registryId", "fisHorseId",
]


def load_horse_map(path: str | Path | None) -> dict[str, str]:
    """Load an optional name/program-based horse-ID mapping from CSV.

    Expected columns: ``horse_name`` *and* ``hippo_horse_id`` at minimum.
    Optional: ``race_id``, ``program_number`` to disambiguate.
    """
    if path is None:
        return {}
    df = pd.read_csv(path)
    mapping: dict[str, str] = {}
    for _, r in df.iterrows():
        hid = str(r["hippo_horse_id"]).strip()
        for key_col in ("horse_name", "horse_id"):
            if key_col in df.columns and pd.notna(r.get(key_col)):
                mapping[str(r[key_col]).strip().lower()] = hid
        if "race_id" in df.columns and "program_number" in df.columns:
            mapping[f"{r['race_id']}::{int(r['program_number'])}"] = hid
    return mapping


def resolve_hippo_ids(starts_df: pd.DataFrame, *,
                      horse_map: dict[str, str] | None = None,
                      api: Optional[HippoApi] = None,
                      name_search: bool = False) -> pd.DataFrame:
    """Attach a ``hippo_horse_id`` column if at all possible.

    Resolution is best-effort; rows that can't be resolved keep a NaN
    in the column and are skipped during enrichment.
    """
    out = starts_df.copy()

    # Strategy (a): JSON already carries the ID under one of many names
    if "hippo_horse_id" not in out.columns:
        out["hippo_horse_id"] = pd.NA
    for col in HIPPO_ID_CANDIDATE_COLS:
        if col in out.columns:
            out["hippo_horse_id"] = out["hippo_horse_id"].fillna(out[col])

    # Strategy (b): manual mapping
    if horse_map:
        def _lookup(row):
            existing = row.get("hippo_horse_id")
            if pd.notna(existing):
                return existing
            key_ids = [
                f"{row['race_id']}::{row['program_number']}",
                str(row.get("horse_id", "")).lower(),
                str(row.get("horse_name", row.get("name", ""))).lower(),
            ]
            for k in key_ids:
                if k and k in horse_map:
                    return horse_map[k]
            return pd.NA

        out["hippo_horse_id"] = out.apply(_lookup, axis=1)

    # Strategy (c): Heppa name search -- opt-in, path not yet confirmed
    if name_search and api is not None:
        unresolved = out[out["hippo_horse_id"].isna()]
        for idx, row in unresolved.iterrows():
            name = row.get("horse_name") or row.get("name")
            if not name:
                continue
            try:
                hid = _heppa_name_search(api, str(name))
            except Exception as e:
                log.warning("name search failed for %s: %s", name, e)
                continue
            if hid:
                out.at[idx, "hippo_horse_id"] = hid

    return out


def _heppa_name_search(api: HippoApi, name: str) -> Optional[str]:
    """Best-effort name lookup. Tries a couple of plausible paths."""
    candidate_paths = [
        "/heppa2_backend/horse/search",
        "/heppa2_backend/search/horses",
        "/heppa2_backend/horses/search",
    ]
    from heppa.discover import fetch_json
    for path in candidate_paths:
        try:
            data = fetch_json(api.client, path, params={"name": name})
        except requests.HTTPError:
            continue
        except Exception:
            continue
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                hid = first.get("horseId") or first.get("id")
                if hid:
                    return str(hid)
    return None


# ---------------------------------------------------------------------------
# Step 3: per-horse enrichment (concurrent)
# ---------------------------------------------------------------------------

@dataclass
class EnrichmentResult:
    df: pd.DataFrame
    resolved: int = 0
    missing: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def enrich_with_history(starts_df: pd.DataFrame, api: HippoApi, *,
                         last_n: int = 20,
                         reference_date: Optional[str] = None,
                         max_workers: int = 4) -> EnrichmentResult:
    """Fill in race_model prior-* fields using heppa horse_starts.

    The input must have a ``hippo_horse_id`` column (see
    :func:`resolve_hippo_ids`). Rows without a resolved ID keep empty
    prior lists and a ``None`` gallop_risk / days_since_last_start.
    """
    out = starts_df.copy()
    horse_ids = out["hippo_horse_id"].dropna().astype(str).unique().tolist()
    features_by_id: dict[str, dict] = {}
    errors: list[dict] = []

    def _fetch(hid: str) -> tuple[str, Optional[dict], Optional[Exception]]:
        try:
            starts = api.horse_starts(hid, page=1, page_size=last_n,
                                       only_results=True)
            feat = to_race_model_features(starts, last_n=last_n,
                                            reference_date=reference_date)
            # Layer in per-year stats for rating features
            try:
                stats = api.horse_stats(hid)
                yearly = stats.yearly
                if not yearly.empty:
                    latest = yearly.iloc[0].to_dict()
                    feat["speed_rating"] = latest.get("car_record_s")
                    feat["class_rating"] = latest.get("earnings_per_start")
                    feat["stamina_rating"] = latest.get("record_s")
            except Exception as e:   # stats optional
                log.debug("stats fetch failed for %s: %s", hid, e)
            return hid, feat, None
        except Exception as e:
            return hid, None, e

    if horse_ids:
        with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
            for hid, feat, err in pool.map(_fetch, horse_ids):
                if err is not None:
                    errors.append({"hippo_horse_id": hid, "error": str(err)})
                else:
                    features_by_id[hid] = feat or {}

    def _apply(row):
        hid = row.get("hippo_horse_id")
        if not hid or pd.isna(hid):
            return row
        feat = features_by_id.get(str(hid))
        if not feat:
            return row
        for k in ("prior_finishes", "prior_km_times", "prior_earnings",
                   "prior_opponent_strengths"):
            if feat.get(k):
                row[k] = feat[k]
        for k in ("days_since_last_start", "gallop_risk",
                   "speed_rating", "class_rating", "stamina_rating"):
            if feat.get(k) is not None:
                row[k] = feat[k]
        return row

    out = out.apply(_apply, axis=1)

    missing = out[out["hippo_horse_id"].isna()][
        ["race_id", "program_number", "horse_name" if "horse_name" in out.columns else "horse_id"]
    ].to_dict(orient="records")

    return EnrichmentResult(
        df=out, resolved=len(horse_ids),
        missing=missing, errors=errors,
    )
