"""Polite HTTP client for swedishhorseracing.com.

Mirrors :class:`heppa.client.HeppaClient`: 1 req/s default, identifying
User-Agent, 3 retries with backoff, disk cache with TTL. The backend
returns JSON under ``/services/...`` paths.
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
from typing import Any, Optional

import requests


DEFAULT_BASE_URL = "https://www.swedishhorseracing.com"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "toto-optimizer/0.1 (+https://github.com/kaivola-beep/betsite)"
)

log = logging.getLogger(__name__)


class TravsportError(RuntimeError):
    """Raised on any non-recoverable adapter error."""


@dataclass
class TravsportClient:
    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    min_request_interval_s: float = 1.0
    max_retries: int = 3
    timeout_s: float = 20.0
    cache_dir: Optional[Path] = None
    cache_ttl_s: float = 600.0
    # Auth pass-throughs. The site returns 401 without a session cookie.
    cookie: Optional[str] = None
    auth_header: Optional[str] = None
    referer: Optional[str] = None
    extra_headers: dict[str, str] = field(default_factory=dict)

    _session: requests.Session = field(init=False, default_factory=requests.Session)
    _last_request_at: float = field(init=False, default=0.0)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self):
        # Swedishhorseracing.com returns 401 unless these browser-XHR
        # headers are present. Values chosen to match a real Chrome
        # request captured from DevTools.
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en,fi-FI;q=0.9,fi;q=0.8,en-US;q=0.7",
            "User-Agent": self.user_agent,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.referer or f"{self.base_url}/races",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        headers.update(self.extra_headers or {})
        self._session.headers.update(headers)
        if self.cache_dir is not None:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def get_json(self, path: str, *, params: Optional[dict] = None,
                 use_cache: bool = True) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        cache_path = (self._cache_path(url, params)
                       if (use_cache and self.cache_dir) else None)

        if cache_path and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < self.cache_ttl_s:
                try:
                    return json.loads(cache_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

        self._throttle()
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.get(url, params=params,
                                           timeout=self.timeout_s)
            except requests.RequestException as e:
                last_exc = e
                self._sleep_backoff(attempt)
                continue
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError as e:
                    raise TravsportError(
                        f"Non-JSON response from {url}: {e}"
                    ) from e
                if cache_path:
                    cache_path.write_text(json.dumps(data, ensure_ascii=False),
                                           encoding="utf-8")
                return data
            if resp.status_code in {429, 500, 502, 503, 504}:
                last_exc = TravsportError(f"HTTP {resp.status_code} from {url}")
                self._sleep_backoff(attempt)
                continue
            raise TravsportError(
                f"HTTP {resp.status_code} from {url}: {resp.text[:300]}"
            )
        raise TravsportError(f"Gave up on {url}: {last_exc}")

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
        return Path(self.cache_dir) / f"{digest}.json"


def from_env() -> TravsportClient:
    base = os.getenv("TRAVSPORT_BASE_URL", DEFAULT_BASE_URL)
    ua = os.getenv("TRAVSPORT_USER_AGENT", DEFAULT_USER_AGENT)
    cache = Path(os.getenv("TRAVSPORT_CACHE_DIR",
                            str(Path.home() / ".cache" / "travsport")))
    interval = float(os.getenv("TRAVSPORT_MIN_INTERVAL", "1.0"))
    return TravsportClient(
        base_url=base, user_agent=ua, cache_dir=cache,
        min_request_interval_s=interval,
        cookie=os.getenv("TRAVSPORT_COOKIE"),
        auth_header=os.getenv("TRAVSPORT_AUTH_HEADER"),
        referer=os.getenv("TRAVSPORT_REFERER",
                           "https://www.swedishhorseracing.com/races"),
    )
