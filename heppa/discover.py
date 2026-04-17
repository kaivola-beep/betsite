"""Small diagnostic helpers for the heppa.hippos.fi scraper.

The live statistics page is a JavaScript SPA: the raw HTML served by
the server doesn't contain ``<table>`` tags. The real data is loaded
client-side via XHR to a JSON endpoint. These helpers surface

* whether the response contains tables at all,
* which URLs referenced by the page look like JSON endpoints, and
* the full list of unique URLs in ``<script>`` / ``href`` / ``src``
  attributes so you can find the right one.

Typical workflow
----------------

>>> from heppa.client import from_env
>>> from heppa.discover import inspect_page
>>> inspect_page(from_env(),
...              "/mobiili/statistics/horses/top/warmblood",
...              params={"startDate": "2023-01-01",
...                      "endDate": "2023-12-31"})

The diagnostic prints candidate endpoints. Copy the most plausible one
and call :func:`fetch_json` directly.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import requests


URL_PATTERN = re.compile(
    r"""(?P<quote>["'])(?P<url>/[A-Za-z0-9_\-/.?=&%]+?|https?://[^"'\s<>]+?)(?P=quote)""",
    re.VERBOSE,
)


def extract_urls(html: str) -> list[str]:
    """Return a sorted, unique list of URLs referenced in the HTML."""
    urls = {m.group("url") for m in URL_PATTERN.finditer(html)}
    return sorted(urls)


def count_tables(html: str) -> int:
    return len(re.findall(r"<table\b", html, flags=re.IGNORECASE))


def candidate_json_endpoints(html: str) -> list[str]:
    """Subset of URLs that look like they serve JSON (statistics data)."""
    urls = extract_urls(html)
    hits = []
    for u in urls:
        low = u.lower()
        if any(k in low for k in ("/api/", "/rest/", "/services/",
                                    "statistics", "horses", "drivers",
                                    "trainers", ".json")):
            if ".js" in low and ".json" not in low:
                continue   # plain JS file, not a data endpoint
            if low.endswith((".css", ".png", ".svg", ".jpg", ".woff",
                              ".woff2", ".ttf", ".ico")):
                continue
            hits.append(u)
    return hits


def inspect_page(client, path: str, *, params: Optional[dict] = None,
                 show_n: int = 25) -> dict:
    """Fetch the page and print a short report. Return structured data."""
    html = client.get_html(path, params=params)
    report = {
        "path": path,
        "params": params,
        "length": len(html),
        "table_count": count_tables(html),
        "total_urls": len(extract_urls(html)),
        "candidates": candidate_json_endpoints(html),
    }
    print(f"Fetched {len(html):,} bytes from {path}")
    print(f"  <table> tags found: {report['table_count']}")
    print(f"  Total referenced URLs: {report['total_urls']}")
    if report["candidates"]:
        print("  Likely JSON endpoints (copy one and retry):")
        for u in report["candidates"][:show_n]:
            print(f"    {u}")
    else:
        print("  No obvious JSON endpoints found in the HTML. Open DevTools "
              "(F12) in your browser, go to Network → XHR, reload the page, "
              "and look for the request that returns the statistics table. "
              "Paste its URL into heppa.discover.fetch_json(..).")
    return report


def fetch_json(client, url: str, *, params: Optional[dict] = None):
    """Call a JSON endpoint through the polite client.

    The URL can be relative (``/heppa-api/statistics/...``) or absolute.
    """
    # Bypass get_html and call session directly for JSON Accept header.
    client._throttle()
    if not url.startswith("http"):
        url = f"{client.base_url}{url}"
    headers = {"Accept": "application/json, text/plain, */*"}
    resp = client._session.get(url, params=params, headers=headers,
                                timeout=client.timeout_s)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return json.loads(resp.text)
