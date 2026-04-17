"""Read-only adapter to Veikkaus Toto-info JSON API.

See README.md for terms of service and usage constraints. Do not use
this package to place bets automatically.
"""
__version__ = "0.1.0"

from .client import VeikkausClient, VeikkausError  # noqa: F401
from .toto import TotoInfo  # noqa: F401
