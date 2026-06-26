"""Felles helpers for fetch-moduler.

Bruker **stdlib `logging`** (ikke structlog) — per bruker-beslutning i
session 10 for å holde CLI-avhengigheter minimale. `structlog` brukes
fortsatt i `bedrock.engine.drivers.trend` fra Fase 1; migrering er ikke
nødvendig med mindre full konvensjon-review ønskes.

Retry-strategi via `tenacity`: 3 forsøk, eksponentiell backoff, ved
`requests.RequestException` (DNS/network/timeout) ELLER HTTP 5xx-svar
(server-side transient — sub-fase 12.10 follow-up post-Spor-F: FRED
returnerer ofte 500 på enkelt-serier).

4xx returneres uendret — permanent caller-feil, skal ikke retries.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

import requests
from tenacity import (
    RetryError,
    Retrying,
    retry_any,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

_log = logging.getLogger(__name__)

T = TypeVar("T")


def _is_5xx_response(response: requests.Response | None) -> bool:
    """tenacity-predikat: retry hvis response.status_code er 500-599."""
    if response is None:
        return False
    return 500 <= response.status_code < 600


def http_get_with_retry(
    url: str,
    params: dict[str, str] | None = None,
    timeout: float = 30.0,
    attempts: int = 3,
    headers: dict[str, str] | None = None,
    retry_on_5xx: bool = True,
    wait_min: float = 1.0,
    wait_max: float = 10.0,
) -> requests.Response:
    """GET med retries + eksponentiell backoff.

    Retries på (a) `requests.RequestException` (DNS/network/timeout)
    og (b) HTTP 5xx-svar (transient server-side). 4xx returneres uendret
    siden de typisk er permanent-feil (auth, malformed query) som ikke
    bedres ved retry.

    Args:
        url: URL som skal hentes.
        params: query-string-parametre (sendes via requests).
        timeout: HTTP-timeout sekunder.
        attempts: antall retry-forsøk (default 3).
        headers: HTTP-headers (User-Agent, custom auth-headers etc.).
            Lagt til i sub-fase 12.5+ session 108 for å støtte fetchers
            som krever custom headers (f.eks. metalcharts X-MC-Token).
        retry_on_5xx: True (default) retries HTTP 5xx; sett False hvis
            caller vil håndtere 5xx selv (f.eks. for fail-fast).
        wait_min: nedre grense for eksponentiell backoff (sekunder).
        wait_max: øvre grense for eksponentiell backoff (sekunder). Hev
            denne (+ `attempts`) for kilder der en kort DNS/nettverks-blipp
            ikke skal felle hele fetch-runet (f.eks. lav-kadens-fetchers).
    """
    if retry_on_5xx:
        retry_predicate = retry_any(
            retry_if_exception_type(requests.RequestException),
            retry_if_result(_is_5xx_response),
        )
    else:
        retry_predicate = retry_if_exception_type(requests.RequestException)

    def _do_request() -> requests.Response:
        _log.debug("http_get url=%s params=%s", url, params)
        response = requests.get(url, params=params, timeout=timeout, headers=headers)
        if retry_on_5xx and 500 <= response.status_code < 600:
            _log.warning(
                "http_get_5xx url=%s status=%d body_preview=%r",
                url,
                response.status_code,
                response.text[:120],
            )
        return response

    retrying = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        retry=retry_predicate,
        reraise=True,
    )
    # Bruk callable-wrapper-modus (ikke iterator) slik at retry_if_result
    # faktisk får inspisere returnen.
    # Når retry_if_result triggrer på siste forsøk reiser tenacity
    # RetryError selv med reraise=True (siden det ikke er en exception å
    # reraise'e). Vi catcher den og returnerer siste response uendret —
    # caller får da samme oppførsel som pre-Spor-F (caller sjekker
    # status_code selv).
    try:
        return retrying(_do_request)
    except RetryError as exc:
        last = exc.last_attempt
        if last is not None and not last.failed:
            return last.result()
        raise


def retry(attempts: int = 3) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Generisk retry-dekorator for fetch-funksjoner.

    Mindre brukt enn `http_get_with_retry` (som er prekonfigurert for HTTP),
    men nyttig for ikke-HTTP-kilder med transiente feil.
    """
    from functools import wraps

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args: object, **kwargs: object) -> T:
            for attempt in Retrying(
                stop=stop_after_attempt(attempts),
                wait=wait_exponential(multiplier=1, min=1, max=10),
                reraise=True,
            ):
                with attempt:
                    return fn(*args, **kwargs)
            raise RuntimeError("retry: exhausted")  # uoppnåelig

        return wrapper

    return decorator
