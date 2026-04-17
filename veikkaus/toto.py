"""High-level Toto-info endpoints.

The methods here each correspond to one REST endpoint documented in the
``veikkaus/sport-games-robot`` reference. They return the raw JSON as a
Python ``dict`` / ``list`` — mapping to the :mod:`race_model` or
:mod:`toto_optimizer` schemas is the job of :mod:`veikkaus.adapters`.

Why not map right away? Because the exact JSON field names on the
Veikkaus API can change between releases; keeping a clean separation
between *fetch* and *map* makes it easy to adjust the mapping without
re-implementing the client.

Endpoints implemented
---------------------
* ``GET /api/toto-info/v1/cards/today``
* ``GET /api/toto-info/v1/card/{cardId}/pools``
* ``GET /api/toto-info/v1/race/{raceId}/runners``
* ``GET /api/toto-info/v1/pool/{poolId}/odds``
* ``GET /api/toto-info/v1/xml/cards.xml`` (returned as raw bytes)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .client import VeikkausClient


@dataclass
class TotoInfo:
    """Typed wrapper around the read-only Toto-info endpoints."""

    client: VeikkausClient

    # ------------------------------------------------------------------
    def cards_today(self) -> list[dict[str, Any]]:
        """List today's cards (one per venue / meeting)."""
        data = self.client.get_json("/api/toto-info/v1/cards/today")
        return _as_list(data, "collection", "cards")

    # ------------------------------------------------------------------
    def card_pools(self, card_id: str | int) -> list[dict[str, Any]]:
        """Return the pools (Voittaja, Sija, T4, T5, T65, T75, T76 ...)
        associated with a card."""
        data = self.client.get_json(f"/api/toto-info/v1/card/{card_id}/pools")
        return _as_list(data, "pools", "collection")

    # ------------------------------------------------------------------
    def race_runners(self, race_id: str | int) -> list[dict[str, Any]]:
        """Return the runners (hevoset) in a single race."""
        data = self.client.get_json(f"/api/toto-info/v1/race/{race_id}/runners")
        return _as_list(data, "runners", "collection")

    # ------------------------------------------------------------------
    def pool_odds(self, pool_id: str | int) -> dict[str, Any]:
        """Return the live odds / pool shares (``peliprosentit``).

        The response typically contains, per runner or per combination,
        the pool share and the derived odds. See
        :func:`veikkaus.adapters.pool_shares_to_dataframe`.
        """
        return self.client.get_json(f"/api/toto-info/v1/pool/{pool_id}/odds")

    # ------------------------------------------------------------------
    def cards_xml(self) -> bytes:
        """Return the XML race programme as raw bytes (useful for
        archival and re-use with offline tools)."""
        # ``get_json`` would fail on XML; do a raw call via the session.
        import requests
        resp = self.client._session.get(
            f"{self.client.base_url}/api/toto-info/v1/xml/cards.xml",
            timeout=self.client.timeout_s,
        )
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _as_list(data: Any, *container_keys: str) -> list[dict[str, Any]]:
    """Return ``data`` as a list of records.

    Veikkaus endpoints sometimes wrap the payload in a ``collection``
    key (`{"collection": [...]}`) and sometimes return a bare list. We
    accept both, plus a few common alternative keys, without needing
    to know the exact shape in advance.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in container_keys:
            val = data.get(key)
            if isinstance(val, list):
                return val
        # Unknown shape — return the dict in a single-element list so
        # the caller can inspect it.
        return [data]
    return []
