# pyright: reportArgumentType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""Tester for EIA Open Data v2 fetcher (sub-fase 12.5+ session 107)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.data.schemas import EIA_INVENTORY_COLS
from bedrock.fetch.eia_inventories import (
    DEFAULT_SERIES,
    fetch_eia,
    fetch_eia_inventories,
    fetch_eia_manual,
    fetch_eia_series,
)

# ---------------------------------------------------------------------------
# Sample EIA v2 JSON-payload
# ---------------------------------------------------------------------------


def _payload(series_id: str, rows: list[dict]) -> dict:
    """Bygg en v2-stil response-dict."""
    return {
        "response": {
            "total": str(len(rows)),
            "data": [
                {
                    "period": r["period"],
                    "series": series_id,
                    "value": r["value"],
                    "units": r.get("units", "MBBL"),
                }
                for r in rows
            ],
        }
    }


# ---------------------------------------------------------------------------
# fetch_eia_series — JSON-injection
# ---------------------------------------------------------------------------


def test_parses_typical_response() -> None:
    spec = DEFAULT_SERIES[0]  # WCESTUS1
    payload = _payload(
        "WCESTUS1",
        [
            {"period": "2026-04-17", "value": "465729", "units": "MBBL"},
            {"period": "2026-04-10", "value": "463804", "units": "MBBL"},
        ],
    )
    df = fetch_eia_series(spec, api_key="DUMMY", raw_response=payload)
    assert len(df) == 2
    assert list(df.columns) == list(EIA_INVENTORY_COLS)
    assert df["series_id"].iloc[0] == "WCESTUS1"
    assert df["value"].iloc[0] == 465729.0
    assert df["units"].iloc[0] == "MBBL"


def test_skips_rows_with_missing_value() -> None:
    spec = DEFAULT_SERIES[0]
    payload = _payload(
        "WCESTUS1",
        [
            {"period": "2026-04-17", "value": "465729", "units": "MBBL"},
            {"period": "2026-04-10", "value": None, "units": "MBBL"},  # droppes
        ],
    )
    df = fetch_eia_series(spec, api_key="DUMMY", raw_response=payload)
    assert len(df) == 1
    assert df["value"].iloc[0] == 465729.0


def test_skips_non_numeric_values() -> None:
    spec = DEFAULT_SERIES[0]
    payload = _payload(
        "WCESTUS1",
        [
            {"period": "2026-04-17", "value": "abc", "units": "MBBL"},  # droppes
            {"period": "2026-04-10", "value": "463804", "units": "MBBL"},
        ],
    )
    df = fetch_eia_series(spec, api_key="DUMMY", raw_response=payload)
    assert len(df) == 1
    assert df["value"].iloc[0] == 463804.0


def test_handles_empty_response() -> None:
    spec = DEFAULT_SERIES[0]
    payload = {"response": {"total": "0", "data": []}}
    df = fetch_eia_series(spec, api_key="DUMMY", raw_response=payload)
    assert df.empty
    assert list(df.columns) == list(EIA_INVENTORY_COLS)


def test_raises_on_missing_response_key() -> None:
    spec = DEFAULT_SERIES[0]
    with pytest.raises(ValueError, match="missing 'response'"):
        fetch_eia_series(spec, api_key="DUMMY", raw_response={"unexpected": True})


def test_raises_on_non_dict_payload() -> None:
    spec = DEFAULT_SERIES[0]
    with pytest.raises(ValueError, match="expected JSON object"):
        fetch_eia_series(spec, api_key="DUMMY", raw_response=[1, 2, 3])


# ---------------------------------------------------------------------------
# fetch_eia_inventories — multi-series sekvensiell
# ---------------------------------------------------------------------------


def test_inventories_combines_all_series() -> None:
    """fetch_eia_inventories kombinerer alle default-series."""
    call_log: list[str] = []

    def _fake(spec, key, *, length=None, timeout=None, raw_response=None):
        call_log.append(spec.series_id)
        return pd.DataFrame(
            {
                "series_id": [spec.series_id],
                "date": ["2026-04-17"],
                "value": [100.0],
                "units": ["MBBL"],
            }
        )

    with patch("bedrock.fetch.eia_inventories.fetch_eia_series", side_effect=_fake):
        df = fetch_eia_inventories(api_key="DUMMY", pacing_sec=0)

    # Sekvensiell: alle 3 series ble kalt i rekkefølge
    assert call_log == [s.series_id for s in DEFAULT_SERIES]
    assert len(df) == 3


def test_inventories_per_series_failure_skips_one() -> None:
    """Én feil aborterer ikke hele kjøringen."""

    def _fake(spec, key, *, length=None, timeout=None, raw_response=None):
        if spec.series_id == "WGTSTUS1":
            raise RuntimeError("HTTP 500")
        return pd.DataFrame(
            {
                "series_id": [spec.series_id],
                "date": ["2026-04-17"],
                "value": [1.0],
                "units": ["MBBL"],
            }
        )

    with patch("bedrock.fetch.eia_inventories.fetch_eia_series", side_effect=_fake):
        df = fetch_eia_inventories(api_key="DUMMY", pacing_sec=0)

    # 2 av 3 lykkedes
    assert len(df) == 2
    assert "WGTSTUS1" not in df["series_id"].tolist()


def test_inventories_raises_when_api_key_missing() -> None:
    """Ingen api_key og ingen env-var → ValueError."""
    with patch("bedrock.fetch.eia_inventories.get_secret", return_value=None):
        with pytest.raises(ValueError, match="mangler API-nøkkel"):
            fetch_eia_inventories(api_key=None, pacing_sec=0)


# ---------------------------------------------------------------------------
# fetch_eia_manual (CSV-fallback)
# ---------------------------------------------------------------------------


def test_manual_returns_empty_when_file_missing(tmp_path: Path) -> None:
    df = fetch_eia_manual(tmp_path / "nope.csv")
    assert df.empty
    assert list(df.columns) == list(EIA_INVENTORY_COLS)


def test_manual_reads_valid_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "eia_inventory.csv"
    pd.DataFrame(
        {
            "series_id": ["WCESTUS1"],
            "date": ["2026-04-17"],
            "value": [465729.0],
            "units": ["MBBL"],
        }
    ).to_csv(csv_path, index=False)

    df = fetch_eia_manual(csv_path)
    assert len(df) == 1
    assert df["value"].iloc[0] == 465729.0


def test_manual_raises_on_missing_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("series_id,date\nWCESTUS1,2026-04-17\n")
    with pytest.raises(ValueError, match="mangler kolonner"):
        fetch_eia_manual(csv_path)


# ---------------------------------------------------------------------------
# fetch_eia (combined)
# ---------------------------------------------------------------------------


def test_combined_uses_api_when_available(tmp_path: Path) -> None:
    api_df = pd.DataFrame(
        {
            "series_id": ["WCESTUS1"],
            "date": ["2026-04-17"],
            "value": [99999.0],
            "units": ["MBBL"],
        }
    )
    with patch(
        "bedrock.fetch.eia_inventories.fetch_eia_inventories",
        return_value=api_df,
    ):
        df = fetch_eia(api_key="DUMMY", csv_path=tmp_path / "missing.csv")
    assert len(df) == 1
    assert df["value"].iloc[0] == 99999.0


def test_combined_falls_back_to_manual(tmp_path: Path) -> None:
    """API feiler → manuell CSV brukes."""
    csv_path = tmp_path / "eia_inventory.csv"
    pd.DataFrame(
        {
            "series_id": ["WCESTUS1"],
            "date": ["2026-04-17"],
            "value": [11111.0],
            "units": ["MBBL"],
        }
    ).to_csv(csv_path, index=False)

    def _fail(*args, **kwargs):
        raise RuntimeError("API outage")

    with patch("bedrock.fetch.eia_inventories.fetch_eia_inventories", side_effect=_fail):
        df = fetch_eia(api_key="DUMMY", csv_path=csv_path)
    assert df["value"].iloc[0] == 11111.0


def test_combined_returns_empty_when_both_fail(tmp_path: Path) -> None:
    def _fail(*args, **kwargs):
        raise RuntimeError("API outage")

    with patch("bedrock.fetch.eia_inventories.fetch_eia_inventories", side_effect=_fail):
        df = fetch_eia(api_key="DUMMY", csv_path=tmp_path / "missing.csv")
    assert df.empty
    assert list(df.columns) == list(EIA_INVENTORY_COLS)


# ---------------------------------------------------------------------------
# Default-series sanity
# ---------------------------------------------------------------------------


def test_default_series_includes_all_three_targets() -> None:
    """CrudeOil + Gasoline + NatGas storage er alle tre i DEFAULT_SERIES."""
    ids = {s.series_id for s in DEFAULT_SERIES}
    assert "WCESTUS1" in ids  # crude
    assert "WGTSTUS1" in ids  # gasoline
    assert "NW2_EPG0_SWO_R48_BCF" in ids  # nat-gas storage
