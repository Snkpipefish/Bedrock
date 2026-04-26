# pyright: reportArgumentType=false
# pandas-stubs har dårlig dekning av DataFrame(columns=list[str]).

"""Tester for ICE Futures Europe COT fetcher (sub-fase 12.5+ session 106)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from bedrock.data.schemas import COT_ICE_COLS
from bedrock.fetch.cot_ice import (
    ICE_MARKETS,
    fetch_cot_ice,
    fetch_cot_ice_manual,
    fetch_cot_ice_remote,
    parse_ice_csv,
)

# ---------------------------------------------------------------------------
# Sample-CSV som matcher ICE-format (CFTC disaggregated-style)
# ---------------------------------------------------------------------------

_SAMPLE_HEADER = (
    "Market_and_Exchange_Names,As_of_Date_Form_MM/DD/YYYY,"
    "Open_Interest_All,"
    "M_Money_Positions_Long_All,M_Money_Positions_Short_All,"
    "Other_Rept_Positions_Long_All,Other_Rept_Positions_Short_All,"
    "Prod_Merc_Positions_Long_All,Prod_Merc_Positions_Short_All,"
    "NonRept_Positions_Long_All,NonRept_Positions_Short_All"
)


def _row(
    market: str,
    date_str: str,
    oi: int = 1_000_000,
    mm_long: int = 100_000,
    mm_short: int = 50_000,
) -> str:
    """Bygg én ICE-CSV-rad som matcher header over."""
    return f'"{market}",{date_str},{oi},{mm_long},{mm_short},15000,12000,400000,450000,6000,5500'


def _sample_csv(rows: list[str]) -> str:
    return _SAMPLE_HEADER + "\n" + "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# parse_ice_csv
# ---------------------------------------------------------------------------


def test_parse_recognizes_brent_crude() -> None:
    csv = _sample_csv([_row("BRENT CRUDE", "01/16/2024")])
    df = parse_ice_csv(csv)
    assert len(df) == 1
    assert df["contract"].iloc[0] == "ice brent crude"
    assert df["report_date"].iloc[0] == "2024-01-16"
    assert df["mm_long"].iloc[0] == 100_000
    assert df["mm_short"].iloc[0] == 50_000
    assert df["open_interest"].iloc[0] == 1_000_000


def test_parse_recognizes_gasoil_and_ttf() -> None:
    csv = _sample_csv(
        [
            _row("LOW SULPHUR GASOIL", "01/16/2024"),
            _row("TTF NATURAL GAS", "01/16/2024"),
        ]
    )
    df = parse_ice_csv(csv)
    contracts = sorted(df["contract"].unique())
    assert contracts == ["ice gasoil", "ice ttf gas"]


def test_parse_skips_unknown_markets() -> None:
    csv = _sample_csv(
        [
            _row("BRENT CRUDE", "01/16/2024"),
            _row("WTI CRUDE OIL", "01/16/2024"),  # ikke i ICE_MARKETS
        ]
    )
    df = parse_ice_csv(csv)
    assert len(df) == 1
    assert df["contract"].iloc[0] == "ice brent crude"


def test_parse_skips_and_options_rows() -> None:
    """Rader merket 'and options' droppes — vi vil kun futures-only-snitt."""
    csv = _sample_csv(
        [
            _row("BRENT CRUDE", "01/16/2024"),
            _row("BRENT CRUDE - and options", "01/16/2024", mm_long=999_999),
        ]
    )
    df = parse_ice_csv(csv)
    assert len(df) == 1
    assert df["mm_long"].iloc[0] == 100_000  # futures-only-raden


def test_parse_handles_yymmdd_date_format() -> None:
    """Hvis bare YYMMDD-felt finnes, parse_date skal håndtere det."""
    csv = (
        "Market_and_Exchange_Names,As_of_Date_In_Form_YYMMDD,"
        "Open_Interest_All,"
        "M_Money_Positions_Long_All,M_Money_Positions_Short_All,"
        "Other_Rept_Positions_Long_All,Other_Rept_Positions_Short_All,"
        "Prod_Merc_Positions_Long_All,Prod_Merc_Positions_Short_All,"
        "NonRept_Positions_Long_All,NonRept_Positions_Short_All\n"
        '"BRENT CRUDE",240116,1000000,100000,50000,15000,12000,400000,450000,6000,5500\n'
    )
    df = parse_ice_csv(csv)
    assert len(df) == 1
    assert df["report_date"].iloc[0] == "2024-01-16"


def test_parse_skips_zero_only_rows() -> None:
    """Rader med 0/0/0 mm/oi droppes (ICE har noen header-separator-rader)."""
    csv = _sample_csv(
        [
            _row("BRENT CRUDE", "01/16/2024", oi=0, mm_long=0, mm_short=0),
            _row("BRENT CRUDE", "01/23/2024"),
        ]
    )
    df = parse_ice_csv(csv)
    assert len(df) == 1
    assert df["report_date"].iloc[0] == "2024-01-23"


def test_parse_dedupe_same_date_and_contract() -> None:
    """Samme (report_date, contract) som forekommer flere ganger → siste vinner."""
    csv = _sample_csv(
        [
            _row("BRENT CRUDE", "01/16/2024", mm_long=100),
            _row("BRENT CRUDE", "01/16/2024", mm_long=999),  # senere → vinner
        ]
    )
    df = parse_ice_csv(csv)
    assert len(df) == 1
    assert df["mm_long"].iloc[0] == 999


def test_parse_returns_empty_on_no_matches() -> None:
    csv = _sample_csv([_row("WTI CRUDE OIL", "01/16/2024")])
    df = parse_ice_csv(csv)
    assert df.empty
    assert list(df.columns) == list(COT_ICE_COLS)


def test_parse_handles_utf8_bom() -> None:
    """ICE-CSV starter ofte med UTF-8-BOM."""
    csv = "\ufeff" + _sample_csv([_row("BRENT CRUDE", "01/16/2024")])
    df = parse_ice_csv(csv)
    assert len(df) == 1


def test_parse_keeps_full_history() -> None:
    """Multi-uke-CSV beholder alle (date, contract) — ikke bare nyeste."""
    csv = _sample_csv(
        [
            _row("BRENT CRUDE", "01/02/2024", mm_long=10),
            _row("BRENT CRUDE", "01/09/2024", mm_long=20),
            _row("BRENT CRUDE", "01/16/2024", mm_long=30),
        ]
    )
    df = parse_ice_csv(csv)
    assert len(df) == 3
    assert df["mm_long"].tolist() == [10, 20, 30]


# ---------------------------------------------------------------------------
# fetch_cot_ice_remote (med raw_text-injection)
# ---------------------------------------------------------------------------


def test_remote_with_injected_text_works() -> None:
    csv = _sample_csv([_row("BRENT CRUDE", "01/16/2024")])
    df = fetch_cot_ice_remote(raw_text=csv)
    assert len(df) == 1


def test_remote_raises_on_empty_parse() -> None:
    csv = _sample_csv([_row("UNKNOWN MARKET", "01/16/2024")])
    with pytest.raises(ValueError, match="0 rows"):
        fetch_cot_ice_remote(raw_text=csv)


# ---------------------------------------------------------------------------
# fetch_cot_ice_manual (CSV fallback)
# ---------------------------------------------------------------------------


def _write_manual_csv(path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows, columns=list(COT_ICE_COLS))
    df.to_csv(path, index=False)


def test_manual_returns_empty_when_file_missing(tmp_path: Path) -> None:
    df = fetch_cot_ice_manual(tmp_path / "nope.csv")
    assert df.empty
    assert list(df.columns) == list(COT_ICE_COLS)


def test_manual_reads_valid_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "cot_ice.csv"
    _write_manual_csv(
        csv_path,
        [
            {
                "report_date": "2026-04-22",
                "contract": "ice brent crude",
                "mm_long": 1000,
                "mm_short": 500,
                "other_long": 100,
                "other_short": 80,
                "comm_long": 4000,
                "comm_short": 4500,
                "nonrep_long": 50,
                "nonrep_short": 40,
                "open_interest": 11000,
            }
        ],
    )
    df = fetch_cot_ice_manual(csv_path)
    assert len(df) == 1
    assert df["mm_long"].iloc[0] == 1000


def test_manual_raises_on_missing_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("report_date,contract\n2026-04-22,ice brent crude\n")
    with pytest.raises(ValueError, match="mangler kolonner"):
        fetch_cot_ice_manual(csv_path)


# ---------------------------------------------------------------------------
# fetch_cot_ice (combined: remote → manual fallback)
# ---------------------------------------------------------------------------


def test_combined_uses_remote_when_available(tmp_path: Path) -> None:
    csv = _sample_csv([_row("BRENT CRUDE", "01/16/2024")])

    def _fake_remote(*, timeout: float = 30.0, raw_text=None, year=None) -> pd.DataFrame:
        return parse_ice_csv(csv)

    with patch("bedrock.fetch.cot_ice.fetch_cot_ice_remote", side_effect=_fake_remote):
        df = fetch_cot_ice(csv_path=tmp_path / "manual.csv")
    assert len(df) == 1
    assert df["contract"].iloc[0] == "ice brent crude"


def test_combined_falls_back_to_manual_when_remote_fails(tmp_path: Path) -> None:
    """Remote feiler → manuell CSV brukes."""
    csv_path = tmp_path / "cot_ice.csv"
    _write_manual_csv(
        csv_path,
        [
            {
                "report_date": "2026-04-22",
                "contract": "ice brent crude",
                "mm_long": 7777,
                "mm_short": 0,
                "other_long": 0,
                "other_short": 0,
                "comm_long": 0,
                "comm_short": 0,
                "nonrep_long": 0,
                "nonrep_short": 0,
                "open_interest": 100,
            }
        ],
    )

    def _failing_remote(*args, **kwargs):
        raise ValueError("simulated network failure")

    with patch("bedrock.fetch.cot_ice.fetch_cot_ice_remote", side_effect=_failing_remote):
        df = fetch_cot_ice(csv_path=csv_path)
    assert len(df) == 1
    assert df["mm_long"].iloc[0] == 7777


def test_combined_returns_empty_when_both_fail(tmp_path: Path) -> None:
    """Både remote og manuell mangler → tom DataFrame, ingen exception."""

    def _failing_remote(*args, **kwargs):
        raise ValueError("simulated network failure")

    with patch("bedrock.fetch.cot_ice.fetch_cot_ice_remote", side_effect=_failing_remote):
        df = fetch_cot_ice(csv_path=tmp_path / "missing.csv")
    assert df.empty
    assert list(df.columns) == list(COT_ICE_COLS)


# ---------------------------------------------------------------------------
# Helsesjekk på ICE_MARKETS-mapping
# ---------------------------------------------------------------------------


def test_ice_markets_canonical_keys() -> None:
    """Sanity: alle 3 canonical-navn finnes i mappingen."""
    canonicals = set(ICE_MARKETS.values())
    assert "ice brent crude" in canonicals
    assert "ice gasoil" in canonicals
    assert "ice ttf gas" in canonicals
