"""Tester for ANP ethanol fetcher."""

from __future__ import annotations

import io
from unittest.mock import Mock, patch

import pytest

from bedrock.fetch.anp_ethanol import (
    SERIES_ID,
    STATE_WEIGHTS,
    AnpFetchError,
    _br_to_float,
    _is_xlsx_bytes,
    _parse_date_dd_mm_yyyy,
    aggregate_to_daily,
    fetch_month,
)


def test_br_to_float_basic() -> None:
    assert _br_to_float("5,99") == 5.99
    assert _br_to_float("4,123") == 4.123


def test_br_to_float_empty_returns_none() -> None:
    assert _br_to_float("") is None
    assert _br_to_float(None) is None


def test_is_xlsx_bytes_detects_zip_magic() -> None:
    assert _is_xlsx_bytes(b"PK\x03\x04stuff") is True
    assert _is_xlsx_bytes(b"plain text") is False


def test_parse_date_dd_mm_yyyy() -> None:
    assert _parse_date_dd_mm_yyyy("01/01/2026") == "2026-01-01"
    assert _parse_date_dd_mm_yyyy("31/12/2025") == "2025-12-31"
    assert _parse_date_dd_mm_yyyy("") is None


def test_state_weights_reasonable() -> None:
    # Sum av Centro-Sul-states ~1.0 (eksport-impact)
    total = sum(STATE_WEIGHTS.values())
    assert 0.95 < total < 1.05


def test_aggregate_filters_non_ethanol() -> None:
    records = [
        {
            "Produto": "GASOLINA",
            "Estado - Sigla": "SP",
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "6,39",
        },
        {
            "Produto": "ETANOL",
            "Estado - Sigla": "SP",
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "4,50",
        },
    ]
    df = aggregate_to_daily(records)
    assert len(df) == 1
    assert df.iloc[0]["value"] == 4.5


def test_aggregate_filters_non_centro_sul() -> None:
    records = [
        {
            "Produto": "ETANOL",
            "Estado - Sigla": "BA",  # not in CS
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "5,00",
        },
        {
            "Produto": "ETANOL",
            "Estado - Sigla": "SP",
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "4,50",
        },
    ]
    df = aggregate_to_daily(records)
    assert len(df) == 1
    assert df.iloc[0]["value"] == 4.5


def test_aggregate_weighted_average() -> None:
    # Bare SP og GO på samme dato — vektet snitt
    records = [
        {
            "Produto": "ETANOL",
            "Estado - Sigla": "SP",
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "4,00",
        },
        {
            "Produto": "ETANOL",
            "Estado - Sigla": "GO",
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "5,00",
        },
    ]
    df = aggregate_to_daily(records)
    # SP w=0.45, GO w=0.15. Vektet: (4*0.45 + 5*0.15) / (0.45+0.15)
    # = (1.8 + 0.75) / 0.60 = 4.25
    assert df.iloc[0]["value"] == pytest.approx(4.25, abs=0.01)


def test_aggregate_skips_invalid_values() -> None:
    records = [
        {
            "Produto": "ETANOL",
            "Estado - Sigla": "SP",
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "0,00",
        },  # 0 — skip
        {
            "Produto": "ETANOL",
            "Estado - Sigla": "SP",
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "999",
        },  # > 20 — skip
        {
            "Produto": "ETANOL",
            "Estado - Sigla": "SP",
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "4,50",
        },
    ]
    df = aggregate_to_daily(records)
    assert len(df) == 1
    assert df.iloc[0]["value"] == 4.5


def test_aggregate_returns_series_id() -> None:
    records = [
        {
            "Produto": "ETANOL",
            "Estado - Sigla": "SP",
            "Data da Coleta": "01/01/2026",
            "Valor de Venda": "4,50",
        },
    ]
    df = aggregate_to_daily(records)
    assert df.iloc[0]["series_id"] == SERIES_ID


def test_fetch_month_csv_success() -> None:
    csv_text = (
        "Produto;Estado - Sigla;Data da Coleta;Valor de Venda;X\nETANOL;SP;01/01/2026;4,50;y\n"
    )
    response = Mock()
    response.status_code = 200
    response.content = b"\xef\xbb\xbf" + csv_text.encode("utf-8")

    with patch("bedrock.fetch.anp_ethanol.http_get_with_retry", return_value=response):
        records = fetch_month(2026, 1)
    assert len(records) == 1
    assert records[0]["Produto"] == "ETANOL"


def test_fetch_month_404_then_xlsx() -> None:
    csv_resp = Mock()
    csv_resp.status_code = 404
    csv_resp.content = b""
    # XLSX response (zip-magic + minimal valid empty xlsx)
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Produto", "Estado - Sigla", "Data da Coleta", "Valor de Venda"])
    ws.append(["ETANOL", "SP", "01/01/2026", 4.50])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_resp = Mock()
    xlsx_resp.status_code = 200
    xlsx_resp.content = buf.getvalue()

    with patch(
        "bedrock.fetch.anp_ethanol.http_get_with_retry",
        side_effect=[csv_resp, xlsx_resp],
    ):
        records = fetch_month(2026, 1)
    assert len(records) == 1


def test_fetch_month_all_fail_raises() -> None:
    response = Mock()
    response.status_code = 404
    response.content = b""

    with patch("bedrock.fetch.anp_ethanol.http_get_with_retry", return_value=response):
        with pytest.raises(AnpFetchError, match="Failed to fetch"):
            fetch_month(2026, 1)
