"""Low-level HTTP client for the Veikkaus JSON API.

Respects the official sport-games-robot guidelines:

* ``X-ESA-API-Key: ROBOT`` header on every request.
* A reasonable ``User-Agent`` (identify yourself).
* Rate limiting: by default at most one request per second.
* At most 4 concurrent requests (we default to sequential).
* Retry with exponential backoff on transient 5xx errors.
* Optional on-disk JSON response cache with TTL (default 10 min) to
  avoid hammering the API when iterating on the adapter locally.

This client is deliberately **read-only**. It exposes no wager
endpoints. The top-level :class:`VeikkausClient` is therefore safe to
use without a logged-in session for public Toto info, which does not
require authentication.

Login helpers are provided for completeness, but the package avoids all
`wager`, `bet` and `ticket` endpoints by design.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests


DEFAULT_BASE_URL = "https://www.veikkaus.fi"
DEFAULT_USER_AGENT = "toto-optimizer/0.1 (+https://github.com/kaivola-beep/betsite; read-only)"

log = logging.getLogger(__name__)


class VeikkausError(RuntimeError):
    """Raised on any non-recoverable API error."""


@dataclass
class VeikkausClient:
    """Thin wrapper around ``requests.Session`` for Veikkaus' API.

    Parameters
    ----------
    base_url
        Root of the API. Override for sandbox / integration tests.
    api_key
        Value of the ``X-ESA-API-Key`` header. Default is ``"ROBOT"``
        as documented in the sport-games-robot reference.
    user_agent
        Identify yourself. Anonymous scrapers are not welcome.
    min_request_interval_s
        Lower bound on the gap between consecutive requests.
    cache_dir
        If set, JSON responses are cached here. ``None`` disables
        caching.
    cache_ttl_s
        Max age of a cached response before it is re-fetched.
    """

    base_url: str = DEFAULT_BASE_URL
    api_key: str = "ROBOT"
    user_agent: str = DEFAULT_USER_AGENT
    min_request_interval_s: float = 1.0
    max_retries: int = 3
    timeout_s: float = 15.0
    cache_dir: Optional[Path] = None
    cache_ttl_s: float = 600.0

    _session: requests.Session = field(init=False, default_factory=requests.Session)
    _last_request_at: float = field(init=False, default=0.0)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self):
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "X-ESA-API-Key": self.api_key,
        })
        if self.cache_dir is not None:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Low-level GET (public; used by higher layers)
    # ------------------------------------------------------------------
    def get_json(self, path: str, *, params: Optional[dict] = None,
                 use_cache: bool = True) -> Any:
        """Perform an authenticated GET and return parsed JSON."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        cache_path = self._cache_path(url, params) if (use_cache and self.cache_dir) else None

        # 1. Cache hit?
        if cache_path and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < self.cache_ttl_s:
                try:
                    return json.loads(cache_path.read_text(encoding="utf-8"))
                except Exception:
                    pass  # fall through to network

        # 2. Rate-limit
        self._throttle()

        # 3. Network with retries
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout_s)
            except requests.RequestException as e:
                last_exc = e
                self._sleep_backoff(attempt)
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError as e:
                    raise VeikkausError(f"Non-JSON response from {url}: {e}") from e
                if cache_path:
                    cache_path.write_text(json.dumps(data, ensure_ascii=False),
                                           encoding="utf-8")
                return data
            if resp.status_code in {429, 500, 502, 503, 504}:
                last_exc = VeikkausError(f"HTTP {resp.status_code} from {url}")
                self._sleep_backoff(attempt)
                continue
            raise VeikkausError(
                f"HTTP {resp.status_code} from {url}: {resp.text[:300]}"
            )

        raise VeikkausError(f"Gave up on {url} after {self.max_retries} retries: {last_exc}")

    # ------------------------------------------------------------------
    # Session login (optional; only needed for account-specific ops)
    # ------------------------------------------------------------------
    def login(self, username: str, password: str) -> dict:
        """Create an authenticated session (cookies stay on the session).

        Typically *not* needed for public Toto info.
        """
        url = f"{self.base_url}/api/bff/v1/sessions"
        resp = self._session.post(
            url,
            json={"type": "STANDARD_LOGIN", "login": username, "password": password},
            timeout=self.timeout_s,
        )
        if resp.status_code != 200:
            raise VeikkausError(f"Login failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _throttle(self):
        with self._lock:
            delta = time.time() - self._last_request_at
            if delta < self.min_request_interval_s:
                time.sleep(self.min_request_interval_s - delta)
            self._last_request_at = time.time()

    def _sleep_backoff(self, attempt: int):
        # 1, 2, 4, 8... seconds
        time.sleep(min(1 * 2 ** attempt, 30))

    def _cache_path(self, url: str, params: Optional[dict]) -> Path:
        import hashlib
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return Path(self.cache_dir) / f"{digest}.json"


# ---------------------------------------------------------------------------
# Env-var convenience constructor
# ---------------------------------------------------------------------------

def from_env() -> VeikkausClient:
    """Construct a client from environment variables.

    Recognised vars:

    * ``VEIKKAUS_BASE_URL`` (default: production URL)
    * ``VEIKKAUS_API_KEY`` (default: ROBOT)
    * ``VEIKKAUS_USER_AGENT``
    * ``VEIKKAUS_CACHE_DIR`` (default: ~/.cache/veikkaus)
    * ``VEIKKAUS_MIN_INTERVAL`` (seconds; default 1.0)
    """
    base = os.getenv("VEIKKAUS_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.getenv("VEIKKAUS_API_KEY", "ROBOT")
    ua = os.getenv("VEIKKAUS_USER_AGENT", DEFAULT_USER_AGENT)
    cache_dir_env = os.getenv("VEIKKAUS_CACHE_DIR")
    cache_dir = Path(cache_dir_env) if cache_dir_env else Path.home() / ".cache" / "veikkaus"
    interval = float(os.getenv("VEIKKAUS_MIN_INTERVAL", "1.0"))
    return VeikkausClient(base_url=base, api_key=api_key, user_agent=ua,
                          cache_dir=cache_dir, min_request_interval_s=interval)
