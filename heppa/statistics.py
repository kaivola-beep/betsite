"""High-level statistics: top horses / drivers / trainers.

Uses :mod:`pandas.read_html` to parse the HTML tables served by the
``/mobiili/statistics/...`` pages. The returned DataFrames have
normalised column names (lowercase, ASCII) so they can be consumed by
the feature engineering layer.

Column normalisation
--------------------
Typical Finnish column headers on the Hippos pages are

* ``Sija`` / rank          -> ``rank``
* ``Nimi`` / ``Hevonen``    -> ``name``
* ``Ohjastaja`` / ``Valm.``-> ``driver`` / ``trainer``
* ``Startit`` / ``St.``     -> ``starts``
* ``V`` / ``V-it``          -> ``wins``
* ``S`` / ``S-it``          -> ``seconds``
* ``K`` / ``K-it``          -> ``thirds``
* ``Voitto-%`` / ``Voi-%``  -> ``win_pct``
* ``Palkkiot``/``€``        -> ``earnings``

If a column can't be matched, the original name is kept so nothing is
lost. Call :meth:`HeppaStatistics.top_horses` etc. and inspect the
result — the ``.attrs["unmapped"]`` list surfaces any columns the
auto-mapper didn't understand.
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

from .client import HeppaClient, HeppaError


Discipline = Literal["warmblood", "coldblood", "all"]


HEADER_MAP = {
    # Horses
    "sija": "rank",
    "nimi": "name",
    "hevonen": "name",
    "startit": "starts",
    "st": "starts",
    "st.": "starts",
    "startti": "starts",
    "v": "wins",
    "v-it": "wins",
    "voitot": "wins",
    "s": "seconds",
    "s-it": "seconds",
    "kakkoset": "seconds",
    "k": "thirds",
    "k-it": "thirds",
    "kolmoset": "thirds",
    "voitto-%": "win_pct",
    "voi-%": "win_pct",
    "sij-%": "place_pct",
    "palkkiot": "earnings",
    "palkkio": "earnings",
    "€": "earnings",
    "eur": "earnings",
    # Drivers / trainers
    "ohjastaja": "driver",
    "kuski": "driver",
    "valmentaja": "trainer",
    "valm.": "trainer",
    "valm": "trainer",
}


@dataclass
class HeppaStatistics:
    client: HeppaClient

    # ------------------------------------------------------------------
    # Public endpoints
    # ------------------------------------------------------------------
    def top_horses(self, discipline: Discipline = "warmblood",
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None,
                   exclude_monte: bool = True) -> pd.DataFrame:
        """Download and parse the top-horses statistics page."""
        path = f"/mobiili/statistics/horses/top/{discipline}"
        return self._fetch_table(path, start_date, end_date, exclude_monte,
                                  subject_key="name")

    def top_drivers(self, discipline: Discipline = "warmblood",
                    start_date: Optional[str] = None,
                    end_date: Optional[str] = None,
                    exclude_monte: bool = True) -> pd.DataFrame:
        path = f"/mobiili/statistics/drivers/top/{discipline}"
        return self._fetch_table(path, start_date, end_date, exclude_monte,
                                  subject_key="driver")

    def top_trainers(self, discipline: Discipline = "warmblood",
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None,
                     exclude_monte: bool = True) -> pd.DataFrame:
        path = f"/mobiili/statistics/trainers/top/{discipline}"
        return self._fetch_table(path, start_date, end_date, exclude_monte,
                                  subject_key="trainer")

    # ------------------------------------------------------------------
    # Parser shared across the three subjects
    # ------------------------------------------------------------------
    def _fetch_table(self, path: str, start_date, end_date, exclude_monte,
                      *, subject_key: str) -> pd.DataFrame:
        params: dict[str, str] = {}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        if exclude_monte:
            params["monte"] = "x"

        html = self.client.get_html(path, params=params)
        return parse_table_html(html, subject_key=subject_key)


# ---------------------------------------------------------------------------
# Parsing (separated out so tests can hit it with fixture HTML)
# ---------------------------------------------------------------------------

def parse_table_html(html: str, *, subject_key: str = "name") -> pd.DataFrame:
    """Parse the first plausible statistics table out of the HTML."""
    try:
        tables = pd.read_html(io.StringIO(html), thousands=" ", decimal=",")
    except (ValueError, ImportError) as e:
        raise HeppaError(f"pandas.read_html failed (is lxml installed?): {e}") from e

    if not tables:
        raise HeppaError("No HTML tables found in response.")

    # Pick the first table that has more than a handful of rows and looks
    # like a statistics listing (has a column that matches a known header).
    candidate = None
    for t in tables:
        headers = [_normalise(str(c)) for c in t.columns]
        if any(h in HEADER_MAP for h in headers):
            candidate = t
            break
    if candidate is None:
        candidate = max(tables, key=len)

    # --- Normalise columns ----------------------------------------------
    new_cols: list[str] = []
    unmapped: list[str] = []
    for c in candidate.columns:
        raw = str(c)
        key = _normalise(raw)
        mapped = HEADER_MAP.get(key)
        new_cols.append(mapped or raw)
        if mapped is None:
            unmapped.append(raw)
    candidate = candidate.copy()
    candidate.columns = new_cols
    candidate.attrs["unmapped"] = unmapped

    # --- Numeric coercion ------------------------------------------------
    for c in ("starts", "wins", "seconds", "thirds"):
        if c in candidate.columns:
            candidate[c] = _to_int(candidate[c])
    for c in ("win_pct", "place_pct"):
        if c in candidate.columns:
            candidate[c] = _to_float(candidate[c])
    if "earnings" in candidate.columns:
        candidate["earnings"] = _to_float(candidate["earnings"])

    # Best-effort rank column
    if "rank" not in candidate.columns:
        candidate.insert(0, "rank", range(1, len(candidate) + 1))

    # Ensure the subject column is present
    if subject_key not in candidate.columns:
        # Fall back to the "name" column if present, else keep as-is
        if "name" in candidate.columns and subject_key != "name":
            candidate = candidate.rename(columns={"name": subject_key})

    return candidate


def _normalise(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    s = s.strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s)
                if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _to_int(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[^\d-]", "", regex=True),
                          errors="coerce").astype("Int64")


def _to_float(s: pd.Series) -> pd.Series:
    s = (s.astype(str)
           .str.replace("\u00A0", " ", regex=False)   # nbsp
           .str.replace(" ", "", regex=False)
           .str.replace(",", ".", regex=False)
           .str.replace(r"[€%]", "", regex=True))
    return pd.to_numeric(s, errors="coerce")
