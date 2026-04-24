"""Driver-registry.

Alle score-drivere registrerer seg via `@register("navn")`. YAML-reglene
refererer til drivere ved navn; Engine slår opp funksjonen i registry ved
runtime.

Driver-kontrakt (se `docs/driver_authoring.md`):

    @register("my_driver")
    def my_driver(store: StoreLike, instrument: str, params: dict) -> float:
        ...

- Signatur er alltid `(store, instrument, params) -> float`
- Returnerer 0..1 (eller -1..1 for bi-direksjonale drivere)
- Ingen side-effekter
- Deterministisk for samme input
- Feil -> return 0.0 og logg (ikke kast)

`store` er typet som `StoreProtocol` her — minimalt for Fase 1. Formaliseres
til `bedrock.data.store.DataStore` i Fase 2.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Typer
# ---------------------------------------------------------------------------


class StoreProtocol(Protocol):
    """Minimal Protocol for data-store.

    Fylles ut i Fase 2 når `DataStore` implementeres. Drivere skrives mot
    denne slik at type-sjekking fanger manglende metoder når store-APIet
    vokser.
    """

    ...


DriverFn = Callable[[Any, str, dict[str, Any]], float]
"""Signatur for alle drivere: `(store, instrument, params) -> float`."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, DriverFn] = {}


def register(name: str) -> Callable[[DriverFn], DriverFn]:
    """Dekorator som legger en driver-funksjon i global registry.

    Kaster `ValueError` hvis navnet allerede er registrert. Dette hindrer at
    to drivere ved et uhell bruker samme navn og "vinner" basert på
    import-rekkefølge.
    """

    def decorator(fn: DriverFn) -> DriverFn:
        if name in _REGISTRY:
            raise ValueError(
                f"Driver '{name}' already registered "
                f"(by {_REGISTRY[name].__module__}.{_REGISTRY[name].__qualname__})"
            )
        _REGISTRY[name] = fn
        return fn

    return decorator


def get(name: str) -> DriverFn:
    """Slå opp driver ved navn. Kaster `KeyError` hvis ukjent."""
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Driver '{name}' not registered. Known drivers: {known}") from None


def all_names() -> list[str]:
    """Returner alle registrerte driver-navn (sortert), for debug/UI."""
    return sorted(_REGISTRY)


def is_registered(name: str) -> bool:
    """Sjekk om et driver-navn finnes i registry."""
    return name in _REGISTRY


# ---------------------------------------------------------------------------
# Auto-register: importer alle driver-moduler slik at @register-kallene kjører.
#
# Ligger sist i modulen for å unngå sirkulær-import (driver-moduler importerer
# `register` fra denne modulen).
# ---------------------------------------------------------------------------

# ruff: noqa: E402, F401
from bedrock.engine.drivers import currency, trend  # noqa: E402
