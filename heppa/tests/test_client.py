"""HeppaClient tests with mocked HTTP."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from heppa.client import HeppaClient, HeppaError


def _resp(status=200, text="<html/>"):
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


def test_get_html_returns_body():
    c = HeppaClient(min_request_interval_s=0.0)
    with patch.object(c._session, "get", return_value=_resp(200, "<table/>")):
        assert c.get_html("/p") == "<table/>"


def test_retries_on_503_then_succeeds():
    c = HeppaClient(min_request_interval_s=0.0, max_retries=2)
    responses = iter([_resp(503), _resp(200, "ok")])
    with patch.object(c._session, "get", side_effect=lambda *a, **k: next(responses)), \
         patch("heppa.client.time.sleep"):
        assert c.get_html("/p") == "ok"


def test_disk_cache_hits_second_call(tmp_path):
    c = HeppaClient(min_request_interval_s=0.0, cache_dir=tmp_path)
    with patch.object(c._session, "get",
                       return_value=_resp(200, "<data/>")) as mock_get:
        c.get_html("/x")
        c.get_html("/x")
    assert mock_get.call_count == 1


def test_raises_on_permanent_error():
    c = HeppaClient(min_request_interval_s=0.0, max_retries=0)
    with patch.object(c._session, "get", return_value=_resp(404, "nope")):
        with pytest.raises(HeppaError):
            c.get_html("/missing")
