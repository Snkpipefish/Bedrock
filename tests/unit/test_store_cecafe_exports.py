"""Tester for cecafe_exports-støtte i DataStore (sub-fase 12.7 D3 A10, session 135)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bedrock.data.schemas import CecafeExportRow
from bedrock.data.store import DataStore


def _row(
    *,
    month: str,
    coffee_type: str = "sum",
    volume_60kg_bags: int | None = 3_000_000,
    fob_value_usd: float | None = 1_000_000_000.0,
    source_pdf: str | None = "https://www.cecafe.com.br/test.pdf",
) -> dict[str, object]:
    return {
        "month": month,
        "coffee_type": coffee_type,
        "volume_60kg_bags": volume_60kg_bags,
        "fob_value_usd": fob_value_usd,
        "source_pdf": source_pdf,
    }


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(tmp_path / "bedrock.db")


def test_cecafe_append_and_get(store: DataStore) -> None:
    df = pd.DataFrame(
        [
            _row(month="2026-03-01", volume_60kg_bags=3_039_876),
            _row(month="2026-02-01", volume_60kg_bags=2_633_488),
        ]
    )
    store.append_cecafe_exports(df)

    out = store.get_cecafe_exports("sum")
    assert len(out) == 2
    assert out["month"].iloc[0] == pd.Timestamp("2026-02-01")  # ASC sort
    assert out["volume_60kg_bags"].iloc[0] == 2_633_488


def test_cecafe_idempotent_replace(store: DataStore) -> None:
    """PK = (month, coffee_type); replay overskriver."""
    store.append_cecafe_exports(
        pd.DataFrame([_row(month="2026-03-01", volume_60kg_bags=1_000_000)])
    )
    store.append_cecafe_exports(
        pd.DataFrame([_row(month="2026-03-01", volume_60kg_bags=9_999_999)])
    )
    out = store.get_cecafe_exports("sum")
    assert len(out) == 1
    assert out["volume_60kg_bags"].iloc[0] == 9_999_999


def test_cecafe_multiple_types_isolated(store: DataStore) -> None:
    """Forskjellige coffee_types deler ikke PK."""
    store.append_cecafe_exports(
        pd.DataFrame(
            [
                _row(month="2026-03-01", coffee_type="arabica", volume_60kg_bags=2_286_909),
                _row(month="2026-03-01", coffee_type="robusta", volume_60kg_bags=368_131),
                _row(month="2026-03-01", coffee_type="sum", volume_60kg_bags=3_039_876),
            ]
        )
    )
    assert store.has_cecafe_exports("arabica") is True
    assert store.has_cecafe_exports("robusta") is True
    assert store.has_cecafe_exports("sum") is True
    arabica = store.get_cecafe_exports("arabica")
    assert arabica["volume_60kg_bags"].iloc[0] == 2_286_909


def test_cecafe_coffee_type_normalized_lowercase(store: DataStore) -> None:
    """coffee_type normaliseres til lowercase i DB."""
    store.append_cecafe_exports(pd.DataFrame([_row(month="2026-03-01", coffee_type="ARABICA")]))
    assert store.has_cecafe_exports("arabica") is True
    assert store.has_cecafe_exports("ARABICA") is True


def test_cecafe_unknown_type_raises_keyerror(store: DataStore) -> None:
    store.append_cecafe_exports(pd.DataFrame([_row(month="2026-03-01")]))
    with pytest.raises(KeyError):
        store.get_cecafe_exports("arabica")


def test_cecafe_has_helper(store: DataStore) -> None:
    assert store.has_cecafe_exports("sum") is False
    store.append_cecafe_exports(pd.DataFrame([_row(month="2026-03-01")]))
    assert store.has_cecafe_exports("sum") is True


def test_cecafe_missing_columns_raises(store: DataStore) -> None:
    df = pd.DataFrame({"month": ["2026-03-01"]})
    with pytest.raises(ValueError, match="missing columns"):
        store.append_cecafe_exports(df)


def test_cecafe_nullable_volume_and_fob_preserved(store: DataStore) -> None:
    """volume_60kg_bags + fob_value_usd er nullable (tåler PDF-parse-glipper)."""
    df = pd.DataFrame(
        [_row(month="2026-03-01", volume_60kg_bags=None, fob_value_usd=None, source_pdf=None)]
    )
    store.append_cecafe_exports(df)
    out = store.get_cecafe_exports("sum")
    assert pd.isna(out["volume_60kg_bags"].iloc[0])
    assert pd.isna(out["fob_value_usd"].iloc[0])
    assert out["source_pdf"].iloc[0] is None


def test_cecafe_from_to_month_filter(store: DataStore) -> None:
    """from_month/to_month filtrerer."""
    store.append_cecafe_exports(
        pd.DataFrame(
            [
                _row(month="2024-12-01"),
                _row(month="2025-06-01"),
                _row(month="2026-03-01"),
            ]
        )
    )
    out = store.get_cecafe_exports("sum", from_month="2025-01-01", to_month="2025-12-31")
    assert len(out) == 1
    assert out["month"].iloc[0] == pd.Timestamp("2025-06-01")


def test_cecafe_pydantic_rejects_unknown_type() -> None:
    """Pydantic-validering blokkerer ukjent coffee_type."""
    import datetime as dt

    with pytest.raises(ValueError, match="coffee_type must be one of"):
        CecafeExportRow(
            month=dt.date(2026, 3, 1),
            coffee_type="bogus",
            volume_60kg_bags=1,
            fob_value_usd=1.0,
        )


def test_cecafe_pydantic_normalizes_uppercase() -> None:
    """Pydantic normaliserer SUM → sum."""
    import datetime as dt

    row = CecafeExportRow(
        month=dt.date(2026, 3, 1),
        coffee_type="SUM",
        volume_60kg_bags=1,
        fob_value_usd=1.0,
    )
    assert row.coffee_type == "sum"
