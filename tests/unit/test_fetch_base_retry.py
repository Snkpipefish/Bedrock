"""Tester for http_get_with_retry retry-policy (post-Spor-F: 5xx-retry)."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from bedrock.fetch.base import _is_5xx_response, http_get_with_retry


def _resp(status_code: int, text: str = "") -> Mock:
    m = Mock(spec=requests.Response)
    m.status_code = status_code
    m.text = text
    return m


def test_is_5xx_response_predicate() -> None:
    assert not _is_5xx_response(None)
    assert not _is_5xx_response(_resp(200))
    assert not _is_5xx_response(_resp(404))
    assert _is_5xx_response(_resp(500))
    assert _is_5xx_response(_resp(502))
    assert _is_5xx_response(_resp(599))
    assert not _is_5xx_response(_resp(600))


def test_returns_2xx_immediately() -> None:
    with patch("bedrock.fetch.base.requests.get", return_value=_resp(200, "ok")):
        r = http_get_with_retry("https://example.com")
        assert r.status_code == 200


def test_4xx_returned_uendret_uten_retry() -> None:
    """4xx er permanent caller-feil, retries ikke."""
    mock_get = Mock(return_value=_resp(404, "not found"))
    with patch("bedrock.fetch.base.requests.get", mock_get):
        r = http_get_with_retry("https://example.com", attempts=3)
        assert r.status_code == 404
    assert mock_get.call_count == 1


def test_5xx_retries_3_ganger_default() -> None:
    """Default retry_on_5xx=True: HTTP 500 retries til attempts uttømt."""
    mock_get = Mock(return_value=_resp(500, "boom"))
    with patch("bedrock.fetch.base.requests.get", mock_get):
        r = http_get_with_retry("https://example.com", attempts=3)
        # Returnerer siste response uendret (raise=False per design)
        assert r.status_code == 500
    assert mock_get.call_count == 3


def test_5xx_recovery_etter_retry() -> None:
    """First call 500, second call 200 → returnerer 200."""
    responses = [_resp(500, "boom"), _resp(200, "ok")]
    mock_get = Mock(side_effect=responses)
    with patch("bedrock.fetch.base.requests.get", mock_get):
        r = http_get_with_retry("https://example.com", attempts=3)
        assert r.status_code == 200
    assert mock_get.call_count == 2


def test_5xx_disabled_via_flag() -> None:
    """retry_on_5xx=False: 500 returneres uten retry."""
    mock_get = Mock(return_value=_resp(500, "boom"))
    with patch("bedrock.fetch.base.requests.get", mock_get):
        r = http_get_with_retry("https://example.com", attempts=3, retry_on_5xx=False)
        assert r.status_code == 500
    assert mock_get.call_count == 1


def test_request_exception_retries() -> None:
    """Eksisterende oppførsel bevart: RequestException retries."""
    mock_get = Mock(side_effect=requests.ConnectionError("dns"))
    with patch("bedrock.fetch.base.requests.get", mock_get):
        with pytest.raises(requests.ConnectionError):
            http_get_with_retry("https://example.com", attempts=3)
    assert mock_get.call_count == 3
