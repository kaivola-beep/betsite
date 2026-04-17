"""Polite HTML-fetching client for heppa.hippos.fi.

Shares a lot of conventions with :class:`veikkaus.client.VeikkausClient`
but the response format is HTML rather than JSON.

Defaults
--------
* 1 request per second minimum interval.
* Identifying User-Agent with contact URL.
* Disk cache with TTL (default 24 h — statistics rarely change).
* 3 retries with exponential backoff on 5xx / 429.

Important: this is HTML scraping, which is inherently fragile. If the
Hippos page structure changes, update :mod:`heppa.statistics`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests


DEFAULT_BASE_URL = "https://heppa.hippos.fi"
DEFAULT_USER_AGENT = (
    "toto-optimizer/0.1 (+https://github.com/kaivola-beep/betsite; "
    "personal research; please contact via GitHub issues if this bothers you)"
)

log = logging.getLogger(__name__)


class HeppaError(RuntimeError):
    """Raised on any non-recoverable scraper error."""


@dataclass
class HeppaClient:
    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    min_request_interval_s: float = 1.0
    max_retries: int = 3
    timeout_s: float = 20.0
    cache_dir: Optional[Path] = None
    cache_ttl_s: float = 24 * 3600.0

    _session: requests.Session = field(init=False, default_factory=requests.Session)
    _last_request_at: float = field(init=False, default=0.0)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self):
        self._session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "fi,en;q=0.7",
        })
        if self.cache_dir is not None:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def get_html(self, path: str, *, params: Optional[dict] = None,
                 use_cache: bool = True) -> str:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        cache_path = self._cache_path(url, params) if (use_cache and self.cache_dir) else None

        if cache_path and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < self.cache_ttl_s:
                return cache_path.read_text(encoding="utf-8")

        self._throttle()
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout_s)
            except requests.RequestException as e:
                last_exc = e
                self._sleep_backoff(attempt)
                continue
            if resp.status_code == 200:
                text = resp.text
                if cache_path:
                    cache_path.write_text(text, encoding="utf-8")
                return text
            if resp.status_code in {429, 500, 502, 503, 504}:
                last_exc = HeppaError(f"HTTP {resp.status_code} from {url}")
                self._sleep_backoff(attempt)
                continue
            raise HeppaError(f"HTTP {resp.status_code} from {url}: {resp.text[:300]}")
        raise HeppaError(f"Gave up on {url}: {last_exc}")

    # ------------------------------------------------------------------
    def _throttle(self):
        with self._lock:
            delta = time.time() - self._last_request_at
            if delta < self.min_request_interval_s:
                time.sleep(self.min_request_interval_s - delta)
            self._last_request_at = time.time()

    def _sleep_backoff(self, attempt: int):
        time.sleep(min(2 ** attempt, 30))

    def _cache_path(self, url: str, params: Optional[dict]) -> Path:
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return Path(self.cache_dir) / f"{digest}.html"


def from_env() -> HeppaClient:
    """Build a HeppaClient from environment variables.

    Recognised:
      HEPPA_BASE_URL, HEPPA_USER_AGENT, HEPPA_CACHE_DIR, HEPPA_MIN_INTERVAL
    """
    base = os.getenv("HEPPA_BASE_URL", DEFAULT_BASE_URL)
    ua = os.getenv("HEPPA_USER_AGENT", DEFAULT_USER_AGENT)
    cache = Path(os.getenv("HEPPA_CACHE_DIR",
                            str(Path.home() / ".cache" / "heppa")))
    interval = float(os.getenv("HEPPA_MIN_INTERVAL", "1.0"))
    return HeppaClient(base_url=base, user_agent=ua, cache_dir=cache,
                       min_request_interval_s=interval)
