"""Read-only adapter to swedishhorseracing.com (Svensk Travsport frontend).

Sister package to :mod:`heppa` for Swedish harness racing data. Same
conventions: polite HTTP client, rate limiting, disk cache, JSON
parsing, and adapters into race_model / ingestion schemas.

Only read endpoints are exposed. This package never places bets.
"""
__version__ = "0.1.0"

from .api import TravsportApi, make_race_id  # noqa: F401
from .client import TravsportClient, TravsportError, from_env  # noqa: F401
