# pyright: reportArgumentType=false
"""Tester for UNICA Brazil sugar/ethanol fetcher (sub-fase 12.5+ session 112)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from bedrock.data.schemas import UNICA_REPORTS_COLS
from bedrock.fetch.unica import (
    br_num,
    fetch_unica,
    fetch_unica_manual,
    fetch_unica_report,
    find_latest_pdf_url,
    parse_unica,
)

# Sample UNICA quinzenal-tekst basert på reell rapport.
_UNICA_TEXT = """
ACOMPANHAMENTO DA SAFRA DA REGIÃO CENTRO-SUL
SAFRA 2025/2026

Posição até 15/04/2026
referente à 1ª quinzena de abril de 2026

TABELA 1 — DADOS ACUMULADOS

açúcar    48,08%    50,61%    [...]
etanol    51,92%    49,39%    [...]

Cana-de-açúcar ¹   617.317   603.667   -2,21%
Açúcar (mil ton)    38.000    40.500    6,58%
Etanol total (mi L)   28.500    28.000   -1,75%
"""


# ---------------------------------------------------------------------------
# br_num
# ---------------------------------------------------------------------------


def test_br_num_pct() -> None:
    assert br_num("-2,21%") == -2.21


def test_br_num_thousand() -> None:
    assert br_num("603.667") == 603667.0


def test_br_num_simple() -> None:
    assert br_num("48,08") == 48.08


def test_br_num_none_handling() -> None:
    assert br_num(None) is None
    assert br_num("") is None
    assert br_num("abc") is None


# ---------------------------------------------------------------------------
# parse_unica
# ---------------------------------------------------------------------------


def test_parse_extracts_position_date() -> None:
    parsed = parse_unica(_UNICA_TEXT)
    assert parsed["position_date"] == "15/04/2026"


def test_parse_extracts_period() -> None:
    parsed = parse_unica(_UNICA_TEXT)
    assert parsed["period"] == "1ª quinzena de abril de 2026"


def test_parse_extracts_crop_year() -> None:
    parsed = parse_unica(_UNICA_TEXT)
    assert parsed["crop_year"] == "2025/2026"


def test_parse_extracts_sugar_mix() -> None:
    parsed = parse_unica(_UNICA_TEXT)
    assert parsed["mix_sugar_pct_prev"] == 48.08
    assert parsed["mix_sugar_pct"] == 50.61


def test_parse_extracts_ethanol_mix() -> None:
    parsed = parse_unica(_UNICA_TEXT)
    assert parsed["mix_ethanol_pct_prev"] == 51.92
    assert parsed["mix_ethanol_pct"] == 49.39


def test_parse_extracts_crush() -> None:
    parsed = parse_unica(_UNICA_TEXT)
    assert parsed["crush_kt_prev"] == 617317.0
    assert parsed["crush_kt"] == 603667.0
    assert parsed["crush_yoy_pct"] == -2.21


def test_parse_returns_empty_for_unrelated_text() -> None:
    parsed = parse_unica("nothing useful here")
    assert parsed == {}


# ---------------------------------------------------------------------------
# find_latest_pdf_url
# ---------------------------------------------------------------------------


def test_find_url_falls_back_to_direct_pdf() -> None:
    """Hvis 'gview?url=' ikke finnes, bruk fallback til direkte .pdf-lenker."""
    response = MagicMock()
    response.status_code = 200
    response.text = '<a href="https://unicadata.com.br/arquivos/pdfs/2026/04/abcdef.pdf">View</a>'
    with patch("bedrock.fetch.unica.http_get_with_retry", return_value=response):
        url = find_latest_pdf_url()
    assert url == "https://unicadata.com.br/arquivos/pdfs/2026/04/abcdef.pdf"


def test_find_url_uses_gview_when_present() -> None:
    response = MagicMock()
    response.status_code = 200
    response.text = (
        '<iframe src="https://docs.google.com/gview?'
        'url=https://unicadata.com.br/arquivos/pdfs/2026/04/abc123.pdf">'
    )
    with patch("bedrock.fetch.unica.http_get_with_retry", return_value=response):
        url = find_latest_pdf_url()
    assert url == "https://unicadata.com.br/arquivos/pdfs/2026/04/abc123.pdf"


def test_find_url_returns_none_on_404() -> None:
    response = MagicMock()
    response.status_code = 404
    response.text = ""
    with patch("bedrock.fetch.unica.http_get_with_retry", return_value=response):
        url = find_latest_pdf_url()
    assert url is None


def test_find_url_returns_none_on_no_match() -> None:
    response = MagicMock()
    response.status_code = 200
    response.text = "<html>no pdf links</html>"
    with patch("bedrock.fetch.unica.http_get_with_retry", return_value=response):
        url = find_latest_pdf_url()
    assert url is None


def test_find_url_handles_http_exception() -> None:
    with patch(
        "bedrock.fetch.unica.http_get_with_retry",
        side_effect=RuntimeError("network down"),
    ):
        url = find_latest_pdf_url()
    assert url is None


# ---------------------------------------------------------------------------
# fetch_unica_report (raw_pdf injection)
# ---------------------------------------------------------------------------


def test_fetch_with_injected_pdf() -> None:
    with patch("bedrock.fetch.unica.pdf_to_text", return_value=_UNICA_TEXT):
        df = fetch_unica_report(report_date=date(2026, 4, 15), raw_pdf=b"fake")
    assert len(df) == 1
    row = df.iloc[0]
    assert row["report_date"] == "2026-04-15"
    assert row["mix_sugar_pct"] == 50.61
    assert row["crop_year"] == "2025/2026"


def test_fetch_returns_empty_when_pdf_unparseable() -> None:
    with patch("bedrock.fetch.unica.pdf_to_text", return_value=None):
        df = fetch_unica_report(raw_pdf=b"unparseable")
    assert df.empty


def test_fetch_returns_empty_when_text_has_no_fields() -> None:
    with patch("bedrock.fetch.unica.pdf_to_text", return_value="totally unrelated"):
        df = fetch_unica_report(raw_pdf=b"fake")
    assert df.empty


# ---------------------------------------------------------------------------
# fetch_unica_manual
# ---------------------------------------------------------------------------


def test_manual_returns_empty_when_missing(tmp_path: Path) -> None:
    df = fetch_unica_manual(tmp_path / "nope.csv")
    assert df.empty


def test_manual_reads_valid_csv(tmp_path: Path) -> None:
    csv = tmp_path / "unica_reports.csv"
    pd.DataFrame(
        [
            dict.fromkeys(UNICA_REPORTS_COLS)
            | {
                "report_date": "2026-04-15",
                "mix_sugar_pct": 50.61,
            }
        ]
    ).to_csv(csv, index=False)
    df = fetch_unica_manual(csv)
    assert len(df) == 1
    assert df["mix_sugar_pct"].iloc[0] == 50.61


def test_manual_raises_on_missing_columns(tmp_path: Path) -> None:
    csv = tmp_path / "bad.csv"
    csv.write_text("report_date,mix_sugar_pct\n2026-04-15,50.61\n")
    with pytest.raises(ValueError, match="mangler kolonner"):
        fetch_unica_manual(csv)


# ---------------------------------------------------------------------------
# fetch_unica (combined)
# ---------------------------------------------------------------------------


def test_combined_uses_pdf_pipeline_when_available(tmp_path: Path) -> None:
    pdf_df = pd.DataFrame(
        [
            dict.fromkeys(UNICA_REPORTS_COLS)
            | {
                "report_date": "2026-04-15",
                "mix_sugar_pct": 50.61,
            }
        ]
    )
    with patch("bedrock.fetch.unica.fetch_unica_report", return_value=pdf_df):
        df = fetch_unica(csv_path=tmp_path / "missing.csv", pacing_sec=0)
    assert len(df) == 1
    assert df["mix_sugar_pct"].iloc[0] == 50.61


def test_combined_falls_back_to_csv(tmp_path: Path) -> None:
    csv = tmp_path / "unica_reports.csv"
    pd.DataFrame(
        [
            dict.fromkeys(UNICA_REPORTS_COLS)
            | {
                "report_date": "2026-04-15",
                "mix_sugar_pct": 99.0,
            }
        ]
    ).to_csv(csv, index=False)
    with patch(
        "bedrock.fetch.unica.fetch_unica_report",
        side_effect=RuntimeError("PDF down"),
    ):
        df = fetch_unica(csv_path=csv, pacing_sec=0)
    assert len(df) == 1
    assert df["mix_sugar_pct"].iloc[0] == 99.0


def test_combined_returns_empty_when_both_fail(tmp_path: Path) -> None:
    with patch(
        "bedrock.fetch.unica.fetch_unica_report",
        side_effect=RuntimeError("PDF down"),
    ):
        df = fetch_unica(csv_path=tmp_path / "missing.csv", pacing_sec=0)
    assert df.empty
    assert list(df.columns) == list(UNICA_REPORTS_COLS)
