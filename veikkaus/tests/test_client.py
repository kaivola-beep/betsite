"""Client tests with mocked HTTP responses."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from veikkaus.client import VeikkausClient, VeikkausError


def _make_response(status=200, payload=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.text = text or (json.dumps(payload) if payload else "")
    r.json = MagicMock(return_value=payload)
    return r


def test_get_json_returns_parsed_body():
    c = VeikkausClient(min_request_interval_s=0.0)
    with patch.object(c._session, "get",
                       return_value=_make_response(200, {"hello": "world"})):
        assert c.get_json("/api/anything") == {"hello": "world"}


def test_retry_on_5xx_then_success(tmp_path):
    c = VeikkausClient(min_request_interval_s=0.0, max_retries=2,
                       cache_dir=tmp_path / "cache")
    responses = iter([_make_response(503), _make_response(200, {"ok": True})])

    def fake_get(*a, **k):
        return next(responses)

    with patch.object(c._session, "get", side_effect=fake_get), \
         patch("veikkaus.client.time.sleep"):
        assert c.get_json("/api/x") == {"ok": True}


def test_raises_on_permanent_error():
    c = VeikkausClient(min_request_interval_s=0.0, max_retries=0)
    with patch.object(c._session, "get",
                       return_value=_make_response(404, text="nope")):
        with pytest.raises(VeikkausError):
            c.get_json("/api/missing")


def test_rate_limit_throttles_requests():
    c = VeikkausClient(min_request_interval_s=0.05)
    calls = []
    with patch.object(c._session, "get",
                       return_value=_make_response(200, {})), \
         patch("veikkaus.client.time.sleep",
                side_effect=lambda s: calls.append(s)):
        c.get_json("/a")
        c.get_json("/b")
    # The second request must have triggered a sleep call
    assert any(s > 0 for s in calls)


def test_disk_cache_round_trip(tmp_path):
    c = VeikkausClient(min_request_interval_s=0.0, cache_dir=tmp_path)
    with patch.object(c._session, "get",
                       return_value=_make_response(200, {"x": 1})) as mock_get:
        c.get_json("/api/once")
        c.get_json("/api/once")
    # Second call should have been served from cache
    assert mock_get.call_count == 1
