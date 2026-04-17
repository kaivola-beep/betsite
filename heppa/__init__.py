"""heppa.hippos.fi statistics scraper (read-only, rate limited, cached).

Use responsibly: this is public data, but the database belongs to Suomen
Hippos ry. Do not republish scraped data; use it only for your own
personal analysis, with a slow request rate and an identifying
User-Agent.
"""
__version__ = "0.1.0"

from .api import HippoApi                   # noqa: F401
from .client import HeppaClient, HeppaError  # noqa: F401
from .statistics import HeppaStatistics      # noqa: F401 (deprecated, HTML-based)
