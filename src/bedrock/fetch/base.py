"""Felles helpers for fetch-moduler.

Bruker **stdlib `logging`** (ikke structlog) — per bruker-beslutning i
session 10 for å holde CLI-avhengigheter minimale. `structlog` brukes
fortsatt i `bedrock.engine.drivers.trend` fra Fase 1; migrering er ikke
nødvendig med mindre full konvensjon-review ønskes.

Retry-strategi via `tenacity`: 3 forsøk, eksponentiell backoff, kun ved
`requests.RequestException` (ikke ved 4xx — de er permanent-feil og
skal ikke gjentas).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

import requests
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_log = logging.getLogger(__name__)

T = TypeVar("T")


def http_get_with_retry(
    url: str,
    params: dict[str, str] | None = None,
    timeout: float = 30.0,
    attempts: int = 3,
) -> requests.Response:
    """GET med 3 retries + eksponentiell backoff på `RequestException`.

    Reiser siste exception hvis alle forsøk feiler. 4xx-responser returneres
    som-er (kaster ikke) — caller må selv sjekke `response.status_code`.
    """
    retrying = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    for attempt in retrying:
        with attempt:
            _log.debug("http_get url=%s params=%s", url, params)
            response = requests.get(url, params=params, timeout=timeout)
            # raise_for_status NOT called her — caller vurderer status
            return response
    # Teoretisk uoppnåelig pga reraise=True, men stiller pyright fornøyd.
    raise RuntimeError("http_get_with_retry: exhausted without return or exception")


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
