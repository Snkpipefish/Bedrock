# pyright: reportArgumentType=false
"""Tester for Conab Brazil crop estimates fetcher (sub-fase 12.5+ session 111)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bedrock.data.schemas import CONAB_ESTIMATES_COLS
from bedrock.fetch.conab import (
    br_num,
    extract_levantamento,
    fetch_cafe_report,
    fetch_conab,
    fetch_conab_manual,
    fetch_grains_report,
    parse_cafe,
    parse_grains,
    pdf_to_text,
)

# Sample-tekst basert på Conab grains-rapport-format
_GRAINS_TEXT = """
7º LEVANTAMENTO
SAFRA 2025/26
TABELA 1 - COMPARATIVO DE ÁREA, PRODUTIVIDADE E PRODUÇÃO

SOJA              47.346,1   48.472,7    2,4   3.622   3.696    2,0   171.480,5   179.151,6    4,5
MILHO TOTAL       21.500,0   22.483,2    4,6   6.560   6.208   (5,4)  141.064,0   139.571,9   (1,1)
TRIGO              3.200,1    3.150,0   (1,6)  3.100   3.080   (0,6)    9.920,3     9.702,0   (2,2)
ALGODÃO - PLUMA    2.085,6    2.041,5   (2,1)  1.957   1.883   (3,8)    4.081,5     3.843,2   (5,8)
"""

_CAFE_TEXT = """
nº1 – Primeiro levantamento
SAFRA 2026
TABELA 1 – ESTIMATIVA DA PRODUÇÃO DE CAFÉ TOTAL

BRASIL              1.875,0    1.850,0   (1,3)    27,7    27,3   (1,4)   52.198,5    50.500,0   (3,3)

TABELA 2 – ESTIMATIVA DA PRODUÇÃO DE CAFÉ ARÁBICA

BRASIL              1.500,0    1.485,0   (1,0)    25,3    25,0   (1,2)   38.000,0    37.125,0   (2,3)

TABELA 3 – ESTIMATIVA DA PRODUÇÃO DE CAFÉ CONILON

BRASIL                375,0      365,0   (2,7)    37,9    36,6   (3,4)   14.198,5    13.375,0   (5,8)
"""


# ---------------------------------------------------------------------------
# br_num
# ---------------------------------------------------------------------------


def test_br_num_simple_decimal() -> None:
    assert br_num("12,4") == 12.4


def test_br_num_with_thousand_separator() -> None:
    assert br_num("179.151,6") == 179151.6


def test_br_num_negative_in_parens() -> None:
    assert br_num("(2,1)") == -2.1


def test_br_num_handles_none() -> None:
    assert br_num(None) is None


def test_br_num_handles_empty() -> None:
    assert br_num("") is None
    assert br_num("   ") is None


def test_br_num_invalid_returns_none() -> None:
    assert br_num("abc") is None


# ---------------------------------------------------------------------------
# extract_levantamento
# ---------------------------------------------------------------------------


def test_extract_grains_levantamento() -> None:
    lev, safra = extract_levantamento(_GRAINS_TEXT)
    assert lev == "7o"
    assert safra == "2025/26"


def test_extract_cafe_levantamento() -> None:
    lev, safra = extract_levantamento(_CAFE_TEXT)
    assert lev == "1o"
    assert safra == "2026"


def test_extract_returns_none_when_missing() -> None:
    lev, safra = extract_levantamento("no header here")
    assert lev is None
    assert safra is None


# ---------------------------------------------------------------------------
# parse_grains
# ---------------------------------------------------------------------------


def test_parse_grains_extracts_all_four_crops() -> None:
    parsed = parse_grains(_GRAINS_TEXT)
    assert "soja" in parsed
    assert "milho" in parsed
    assert "trigo" in parsed
    assert "algodao" in parsed


def test_parse_grains_soja_values() -> None:
    parsed = parse_grains(_GRAINS_TEXT)
    soja = parsed["soja"]
    assert soja["production"] == 179151.6
    assert soja["production_units"] == "kt"
    assert soja["area_kha"] == 48472.7
    assert soja["yield_value"] == 3696.0
    assert soja["yoy_change_pct"] == 4.5


def test_parse_grains_negative_yoy_in_parens() -> None:
    """ALGODÃO har negativ YoY som (5,8) → -5.8."""
    parsed = parse_grains(_GRAINS_TEXT)
    assert parsed["algodao"]["yoy_change_pct"] == -5.8


def test_parse_grains_empty_text() -> None:
    assert parse_grains("") == {}


# ---------------------------------------------------------------------------
# parse_cafe
# ---------------------------------------------------------------------------


def test_parse_cafe_extracts_all_three_tables() -> None:
    parsed = parse_cafe(_CAFE_TEXT)
    assert "cafe_total" in parsed
    assert "cafe_arabica" in parsed
    assert "cafe_conilon" in parsed


def test_parse_cafe_total_values() -> None:
    parsed = parse_cafe(_CAFE_TEXT)
    total = parsed["cafe_total"]
    assert total["production"] == 50500.0
    assert total["production_units"] == "ksacas"
    assert total["yield_units"] == "sacasha"
    assert total["yoy_change_pct"] == -3.3


def test_parse_cafe_empty_text() -> None:
    assert parse_cafe("") == {}


# ---------------------------------------------------------------------------
# pdf_to_text (begge ekstraktorer mocket)
# ---------------------------------------------------------------------------


def test_pdf_to_text_uses_pdftotext_when_available() -> None:
    with patch("bedrock.fetch.conab._pdftotext", return_value="pdftotext output"):
        result = pdf_to_text(b"fake pdf bytes")
    assert result == "pdftotext output"


def test_pdf_to_text_falls_back_to_pypdf() -> None:
    with (
        patch("bedrock.fetch.conab._pdftotext", return_value=None),
        patch("bedrock.fetch.conab._pypdf_text", return_value="pypdf output"),
    ):
        result = pdf_to_text(b"fake pdf bytes")
    assert result == "pypdf output"


def test_pdf_to_text_returns_none_when_both_fail() -> None:
    with (
        patch("bedrock.fetch.conab._pdftotext", return_value=None),
        patch("bedrock.fetch.conab._pypdf_text", return_value=None),
    ):
        assert pdf_to_text(b"bad pdf") is None


def test_pdf_to_text_empty_bytes() -> None:
    """Tom bytes → None."""
    with (
        patch("bedrock.fetch.conab._pdftotext", return_value=None),
        patch("bedrock.fetch.conab._pypdf_text", return_value=None),
    ):
        assert pdf_to_text(b"") is None


# ---------------------------------------------------------------------------
# fetch_grains_report (raw_pdf injection)
# ---------------------------------------------------------------------------


def test_fetch_grains_with_injected_pdf() -> None:
    with patch("bedrock.fetch.conab.pdf_to_text", return_value=_GRAINS_TEXT):
        df = fetch_grains_report(report_date=date(2026, 4, 15), raw_pdf=b"fake")
    assert len(df) == 4
    assert set(df["commodity"]) == {"soja", "milho", "trigo", "algodao"}
    assert df["report_date"].iloc[0] == "2026-04-15"
    assert df["levantamento"].iloc[0] == "7o"


def test_fetch_grains_returns_empty_when_pdf_unparseable() -> None:
    with patch("bedrock.fetch.conab.pdf_to_text", return_value=None):
        df = fetch_grains_report(raw_pdf=b"unparseable")
    assert df.empty


def test_fetch_grains_returns_empty_when_text_has_no_rows() -> None:
    with patch("bedrock.fetch.conab.pdf_to_text", return_value="no tables here"):
        df = fetch_grains_report(raw_pdf=b"fake")
    assert df.empty


# ---------------------------------------------------------------------------
# fetch_cafe_report
# ---------------------------------------------------------------------------


def test_fetch_cafe_with_injected_pdf() -> None:
    with patch("bedrock.fetch.conab.pdf_to_text", return_value=_CAFE_TEXT):
        df = fetch_cafe_report(report_date=date(2026, 4, 15), raw_pdf=b"fake")
    assert len(df) == 3
    assert set(df["commodity"]) == {"cafe_total", "cafe_arabica", "cafe_conilon"}
    assert df["production_units"].iloc[0] == "ksacas"
    assert df["levantamento"].iloc[0] == "1o"


# ---------------------------------------------------------------------------
# fetch_conab_manual
# ---------------------------------------------------------------------------


def test_manual_returns_empty_when_missing(tmp_path: Path) -> None:
    df = fetch_conab_manual(tmp_path / "nope.csv")
    assert df.empty


def test_manual_reads_valid_csv(tmp_path: Path) -> None:
    csv = tmp_path / "conab_estimates.csv"
    pd.DataFrame(
        [
            {
                "report_date": "2026-04-15",
                "commodity": "soja",
                "levantamento": "7o",
                "safra": "2025/26",
                "production": 179151.6,
                "production_units": "kt",
                "area_kha": 48472.7,
                "yield_value": 3696.0,
                "yield_units": "kgha",
                "yoy_change_pct": 4.5,
                "mom_change_pct": None,
            }
        ]
    ).to_csv(csv, index=False)

    df = fetch_conab_manual(csv)
    assert len(df) == 1
    assert df["production"].iloc[0] == 179151.6


def test_manual_raises_on_missing_columns(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    csv.write_text("report_date,commodity\n2026-04-15,soja\n")
    with pytest.raises(ValueError, match="mangler kolonner"):
        fetch_conab_manual(csv)


# ---------------------------------------------------------------------------
# fetch_conab (combined)
# ---------------------------------------------------------------------------


def test_combined_calls_grains_and_cafe(tmp_path: Path) -> None:
    grains_df = pd.DataFrame(
        [
            {
                "report_date": "2026-04-15",
                "commodity": "soja",
                "levantamento": "7o",
                "safra": "2025/26",
                "production": 179000,
                "production_units": "kt",
                "area_kha": 48000,
                "yield_value": 3700,
                "yield_units": "kgha",
                "yoy_change_pct": 4.5,
                "mom_change_pct": None,
            }
        ]
    )
    cafe_df = pd.DataFrame(
        [
            {
                "report_date": "2026-04-15",
                "commodity": "cafe_total",
                "levantamento": "1o",
                "safra": "2026",
                "production": 50500,
                "production_units": "ksacas",
                "area_kha": 1850,
                "yield_value": 27.3,
                "yield_units": "sacasha",
                "yoy_change_pct": -3.2,
                "mom_change_pct": None,
            }
        ]
    )

    with (
        patch("bedrock.fetch.conab.fetch_grains_report", return_value=grains_df),
        patch("bedrock.fetch.conab.fetch_cafe_report", return_value=cafe_df),
    ):
        df = fetch_conab(csv_path=tmp_path / "missing.csv", pacing_sec=0)

    assert len(df) == 2
    assert set(df["commodity"]) == {"soja", "cafe_total"}


def test_combined_falls_back_to_csv(tmp_path: Path) -> None:
    csv = tmp_path / "conab_estimates.csv"
    pd.DataFrame(
        [
            {
                "report_date": "2026-04-15",
                "commodity": "soja",
                "levantamento": "7o",
                "safra": "2025/26",
                "production": 999999,
                "production_units": "kt",
                "area_kha": 48000,
                "yield_value": 3700,
                "yield_units": "kgha",
                "yoy_change_pct": 4.5,
                "mom_change_pct": None,
            }
        ]
    ).to_csv(csv, index=False)

    with (
        patch(
            "bedrock.fetch.conab.fetch_grains_report",
            side_effect=RuntimeError("PDF down"),
        ),
        patch("bedrock.fetch.conab.fetch_cafe_report", side_effect=RuntimeError("PDF down")),
    ):
        df = fetch_conab(csv_path=csv, pacing_sec=0)

    assert len(df) == 1
    assert df["production"].iloc[0] == 999999


def test_combined_returns_empty_when_all_fail(tmp_path: Path) -> None:
    with (
        patch(
            "bedrock.fetch.conab.fetch_grains_report",
            side_effect=RuntimeError("PDF down"),
        ),
        patch("bedrock.fetch.conab.fetch_cafe_report", side_effect=RuntimeError("PDF down")),
    ):
        df = fetch_conab(csv_path=tmp_path / "missing.csv", pacing_sec=0)
    assert df.empty
    assert list(df.columns) == list(CONAB_ESTIMATES_COLS)


# Suppress unused-import warning
_ = MagicMock
