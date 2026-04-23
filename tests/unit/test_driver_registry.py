"""Tester for driver-registry + @register-dekorator."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bedrock.engine import drivers


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    """Snapshot + restore registry rundt hver test.

    Uten denne ville tester forurense hverandres navnespace — særlig siden
    `@register` kaster ved duplikate navn.
    """
    snapshot = dict(drivers._REGISTRY)
    yield
    drivers._REGISTRY.clear()
    drivers._REGISTRY.update(snapshot)


def test_register_stores_function_under_name() -> None:
    @drivers.register("test_a")
    def my_driver(store: object, instrument: str, params: dict) -> float:
        return 0.5

    assert drivers.is_registered("test_a")
    assert drivers.get("test_a") is my_driver


def test_register_duplicate_name_raises() -> None:
    @drivers.register("test_dup")
    def first(store: object, instrument: str, params: dict) -> float:
        return 0.0

    with pytest.raises(ValueError, match="already registered"):

        @drivers.register("test_dup")
        def second(store: object, instrument: str, params: dict) -> float:
            return 1.0


def test_get_unknown_driver_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="not registered"):
        drivers.get("this_does_not_exist")


def test_all_names_returns_sorted() -> None:
    @drivers.register("zeta")
    def _z(store: object, instrument: str, params: dict) -> float:
        return 0.0

    @drivers.register("alpha")
    def _a(store: object, instrument: str, params: dict) -> float:
        return 0.0

    names = drivers.all_names()
    assert names.index("alpha") < names.index("zeta")


def test_registered_driver_callable_with_expected_signature() -> None:
    @drivers.register("test_call")
    def my_driver(store: object, instrument: str, params: dict) -> float:
        return 0.75

    fn = drivers.get("test_call")
    assert fn(None, "Gold", {"tf": "D1"}) == 0.75
