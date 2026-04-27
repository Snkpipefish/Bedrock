# pyright: reportArgumentType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""Tester for COMEX-fetcher (sub-fase 12.5+ session 108)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.data.schemas import COMEX_INVENTORY_COLS
from bedrock.fetch.comex import (
    DEFAULT_METALS,
    fetch_comex,
    fetch_comex_manual,
    fetch_comex_metal,
)


def _payload(
    *,
    success: bool = True,
    registered: float = 15_000_000.0,
    eligible: float = 13_000_000.0,
    total: float = 25_000_000.0,
    date: str = "2026-04-24",
) -> dict:
    return {
        "success": success,
        "data": {
            "registered": registered,
            "eligible": eligible,
            "total": total,
            "date": date,
        },
    }


# ---------------------------------------------------------------------------
# fetch_comex_metal — JSON-injection
# ---------------------------------------------------------------------------


def test_parses_typical_gold_response() -> None:
    spec = DEFAULT_METALS[0]  # XAU/gold
    df = fetch_comex_metal(spec, token="DUMMY", raw_response=_payload())
    assert len(df) == 1
    assert list(df.columns) == list(COMEX_INVENTORY_COLS)
    row = df.iloc[0]
    assert row["metal"] == "gold"
    assert row["registered"] == 15_000_000.0
    assert row["eligible"] == 13_000_000.0
    assert row["units"] == "oz"
    assert row["date"] == "2026-04-24"


def test_copper_no_eligible_split() -> None:
    """Når API gir reg=0 + elig=0 + total>0 for HG, settes reg=total."""
    copper_spec = DEFAULT_METALS[2]
    payload = _payload(registered=0, eligible=0, total=32500)
    df = fetch_comex_metal(copper_spec, token="DUMMY", raw_response=payload)
    row = df.iloc[0]
    assert row["registered"] == 32500.0
    assert row["eligible"] == 0.0
    assert row["total"] == 32500.0
    assert row["units"] == "st"


def test_copper_with_separate_reg_elig_preserved() -> None:
    """Hvis API gir reg+elig separat for HG, ikke mash sammen."""
    copper_spec = DEFAULT_METALS[2]
    payload = _payload(registered=20000, eligible=12500, total=32500)
    df = fetch_comex_metal(copper_spec, token="DUMMY", raw_response=payload)
    row = df.iloc[0]
    assert row["registered"] == 20000.0
    assert row["eligible"] == 12500.0


def test_returns_empty_when_unsuccessful() -> None:
    spec = DEFAULT_METALS[0]
    df = fetch_comex_metal(spec, token="DUMMY", raw_response=_payload(success=False))
    assert df.empty
    assert list(df.columns) == list(COMEX_INVENTORY_COLS)


def test_returns_empty_when_data_missing() -> None:
    spec = DEFAULT_METALS[0]
    df = fetch_comex_metal(spec, token="DUMMY", raw_response={"success": True, "data": None})
    assert df.empty


def test_returns_empty_when_date_missing() -> None:
    spec = DEFAULT_METALS[0]
    bad = {"success": True, "data": {"registered": 1, "total": 2}}  # no date
    df = fetch_comex_metal(spec, token="DUMMY", raw_response=bad)
    assert df.empty


def test_raises_on_non_dict_payload() -> None:
    spec = DEFAULT_METALS[0]
    with pytest.raises(ValueError, match="expected JSON object"):
        fetch_comex_metal(spec, token="DUMMY", raw_response=[1, 2, 3])


def test_raises_on_non_numeric_values() -> None:
    spec = DEFAULT_METALS[0]
    bad = {
        "success": True,
        "data": {"registered": "abc", "eligible": 1, "total": 1, "date": "2026-04-24"},
    }
    with pytest.raises(ValueError, match="non-numeric"):
        fetch_comex_metal(spec, token="DUMMY", raw_response=bad)


# ---------------------------------------------------------------------------
# fetch_comex — multi-metal sekvensiell
# ---------------------------------------------------------------------------


def test_combines_all_metals() -> None:
    """fetch_comex henter alle DEFAULT_METALS sekvensielt."""
    call_log: list[str] = []

    def _fake(spec, token, *, timeout=None, raw_response=None):
        call_log.append(spec.symbol)
        return pd.DataFrame(
            [
                {
                    "metal": spec.metal,
                    "date": "2026-04-24",
                    "registered": 1.0,
                    "eligible": 0.0,
                    "total": 1.0,
                    "units": spec.units,
                }
            ],
            columns=list(COMEX_INVENTORY_COLS),
        )

    with (
        patch("bedrock.fetch.comex._fetch_token", return_value="TOKEN"),
        patch("bedrock.fetch.comex.fetch_comex_metal", side_effect=_fake),
    ):
        df = fetch_comex(pacing_sec=0)

    assert call_log == [s.symbol for s in DEFAULT_METALS]
    assert len(df) == 3


def test_per_metal_failure_skips_one() -> None:
    """Én metallfeil aborterer ikke kjøringen."""

    def _fake(spec, token, *, timeout=None, raw_response=None):
        if spec.symbol == "XAG":
            raise RuntimeError("HTTP 500")
        return pd.DataFrame(
            [
                {
                    "metal": spec.metal,
                    "date": "2026-04-24",
                    "registered": 1.0,
                    "eligible": 0.0,
                    "total": 1.0,
                    "units": spec.units,
                }
            ],
            columns=list(COMEX_INVENTORY_COLS),
        )

    with (
        patch("bedrock.fetch.comex._fetch_token", return_value="TOKEN"),
        patch("bedrock.fetch.comex.fetch_comex_metal", side_effect=_fake),
    ):
        df = fetch_comex(pacing_sec=0)

    assert len(df) == 2
    assert "silver" not in df["metal"].tolist()


def test_falls_back_to_csv_on_token_failure(tmp_path: Path) -> None:
    """Hvis token-endepunkt feiler, faller fetch_comex tilbake på CSV."""
    csv_path = tmp_path / "comex_inventory.csv"
    pd.DataFrame(
        [
            {
                "metal": "gold",
                "date": "2026-04-24",
                "registered": 15_000_000.0,
                "eligible": 13_000_000.0,
                "total": 28_000_000.0,
                "units": "oz",
            }
        ]
    ).to_csv(csv_path, index=False)

    with patch("bedrock.fetch.comex._fetch_token", side_effect=RuntimeError("token failed")):
        df = fetch_comex(csv_path=csv_path, pacing_sec=0)

    assert len(df) == 1
    assert df["metal"].iloc[0] == "gold"


def test_returns_empty_when_both_api_and_csv_fail(tmp_path: Path) -> None:
    with patch("bedrock.fetch.comex._fetch_token", side_effect=RuntimeError("API down")):
        df = fetch_comex(csv_path=tmp_path / "missing.csv", pacing_sec=0)
    assert df.empty
    assert list(df.columns) == list(COMEX_INVENTORY_COLS)


# ---------------------------------------------------------------------------
# Manual CSV
# ---------------------------------------------------------------------------


def test_manual_returns_empty_when_file_missing(tmp_path: Path) -> None:
    df = fetch_comex_manual(tmp_path / "nope.csv")
    assert df.empty
    assert list(df.columns) == list(COMEX_INVENTORY_COLS)


def test_manual_reads_valid_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "comex_inventory.csv"
    pd.DataFrame(
        [
            {
                "metal": "gold",
                "date": "2026-04-24",
                "registered": 15_000_000.0,
                "eligible": 13_000_000.0,
                "total": 28_000_000.0,
                "units": "oz",
            }
        ]
    ).to_csv(csv_path, index=False)

    df = fetch_comex_manual(csv_path)
    assert len(df) == 1
    assert df["registered"].iloc[0] == 15_000_000.0


def test_manual_raises_on_missing_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("metal,date\ngold,2026-04-24\n")
    with pytest.raises(ValueError, match="mangler kolonner"):
        fetch_comex_manual(csv_path)


# ---------------------------------------------------------------------------
# Default-metals sanity
# ---------------------------------------------------------------------------


def test_default_metals_includes_gold_silver_copper() -> None:
    metals = {s.metal for s in DEFAULT_METALS}
    assert metals == {"gold", "silver", "copper"}


def test_default_metals_units_correct() -> None:
    """Gull/sølv = oz, kobber = st."""
    spec_by = {s.metal: s for s in DEFAULT_METALS}
    assert spec_by["gold"].units == "oz"
    assert spec_by["silver"].units == "oz"
    assert spec_by["copper"].units == "st"
