"""End-to-end ingestion: Veikkaus card -> heppa history -> scored predictions.

This package orchestrates the three read-only data packages
(:mod:`veikkaus`, :mod:`heppa`) and the prediction stack
(:mod:`race_model`) into a single CLI usable against a live Toto card.
"""
__version__ = "0.1.0"

from .enrichment import enrich_with_history, fetch_card_starts  # noqa: F401
from .scoring import score_simple, softmax_within_race          # noqa: F401
