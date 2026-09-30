"""Tester for ANP ethanol fetcher."""

from __future__ import annotations

import io
from unittest.mock import Mock, patch

import pytest

from bedrock.fetch.anp_ethanol import (
    SERIES_ID,
    STATE_WEIGHTS,
    URL_TMPL_NEW,
    AnpFetchError,
    _br_to_float,
    _is_xlsx_bytes,
    _month_from_filename,
    _parse_date_dd_mm_yyyy,
    aggregate_to_daily,
    discover_month_urls,
    fetch_month,
    parse_listing,
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


# --- Fil-oppdagelse via mappe-listing (2026-09-30: ANP navngir inkonsistent) ---

_BASE = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan"

_LISTING_2026 = f"""
<a href="{_BASE}/2026/">2026</a>
<a href="{_BASE}/2026/01-dados-abertos-precos-diesel-gnv.csv/view">x</a>
<a href="{_BASE}/2026/01-dados-abertos-precos-gasolina-etanol.csv/view">x</a>
<a href="{_BASE}/2026/01-dados-abertos-precos-glp.csv/view">x</a>
<a href="{_BASE}/2026/02-cados-abertos-preco-gasolina-etanol.csv/view">typo</a>
<a href="{_BASE}/2026/04-dados-abertos-precos-gasolina-etanol/view">uten ext</a>
<a href="{_BASE}/2026/06-dados-abertos-precos-2026-06-gasolina-etanol.csv/view">dato i navn</a>
<a href="{_BASE}/2026/07-dados-abertos-precos-gasolina-etanol.csv/view">x</a>
<a href="{_BASE}/2026/07-dados-abertos-precos-gasolina-etanol.csv/view">duplikat</a>
<a href="{_BASE}/2025/precos-gasolina-etanol-12.csv/view">feil år</a>
"""


def test_month_from_filename_variants() -> None:
    assert _month_from_filename("01-dados-abertos-precos-gasolina-etanol.csv") == 1
    assert _month_from_filename("02-cados-abertos-preco-gasolina-etanol.csv") == 2
    assert _month_from_filename("04-dados-abertos-precos-gasolina-etanol") == 4
    assert _month_from_filename("06-dados-abertos-precos-2026-06-gasolina-etanol.csv") == 6
    assert _month_from_filename("precos-gasolina-etanol-07.csv") == 7
    assert _month_from_filename("precos-gasolina-etanol-11") == 11
    assert _month_from_filename("precos-gasolina-etanol.csv") is None
    assert _month_from_filename("13-dados-abertos-precos-gasolina-etanol.csv") is None


def test_parse_listing_picks_ethanol_files_per_month() -> None:
    found = parse_listing(_LISTING_2026, 2026)
    assert sorted(found) == [1, 2, 4, 6, 7]
    assert found[2] == [f"{_BASE}/2026/02-cados-abertos-preco-gasolina-etanol.csv"]
    assert found[4] == [f"{_BASE}/2026/04-dados-abertos-precos-gasolina-etanol"]
    assert found[6] == [f"{_BASE}/2026/06-dados-abertos-precos-2026-06-gasolina-etanol.csv"]
    # «/view» strippet, duplikat kollapset
    assert found[7] == [f"{_BASE}/2026/07-dados-abertos-precos-gasolina-etanol.csv"]


def test_parse_listing_old_style_and_relative_href() -> None:
    html = (
        '<a href="/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/shpc/dsan/2025/'
        'precos-gasolina-etanol-03.csv/view">x</a>'
    )
    found = parse_listing(html, 2025)
    assert found == {3: [f"{_BASE}/2025/precos-gasolina-etanol-03.csv"]}


def test_parse_listing_empty_on_no_matches() -> None:
    assert parse_listing("<html><body>ingenting</body></html>", 2026) == {}


def test_fetch_month_tries_discovered_url_first() -> None:
    csv_text = "Produto;Estado - Sigla;Data da Coleta;Valor de Venda\nETANOL;SP;03/02/2026;4,50\n"
    response = Mock()
    response.status_code = 200
    response.content = csv_text.encode("utf-8")
    discovered = f"{_BASE}/2026/02-cados-abertos-preco-gasolina-etanol.csv"

    with patch("bedrock.fetch.anp_ethanol.http_get_with_retry", return_value=response) as get:
        records = fetch_month(2026, 2, candidates=[discovered])
    assert len(records) == 1
    assert get.call_args_list[0].args[0] == discovered


def test_fetch_month_falls_back_to_templates_after_candidates() -> None:
    fail = Mock()
    fail.status_code = 404
    fail.content = b""
    ok = Mock()
    ok.status_code = 200
    ok.content = (
        b"Produto;Estado - Sigla;Data da Coleta;Valor de Venda\nETANOL;SP;03/02/2026;4,50\n"
    )

    with patch("bedrock.fetch.anp_ethanol.http_get_with_retry", side_effect=[fail, ok]) as get:
        records = fetch_month(2026, 2, candidates=[f"{_BASE}/2026/dead-link"])
    assert len(records) == 1
    assert get.call_args_list[1].args[0] == URL_TMPL_NEW.format(year=2026, month=2, ext="csv")


def test_discover_month_urls_returns_empty_on_http_error() -> None:
    response = Mock()
    response.status_code = 403
    response.text = ""
    with patch("bedrock.fetch.anp_ethanol.http_get_with_retry", return_value=response):
        assert discover_month_urls(2026) == {}


def test_discover_month_urls_follows_pagination() -> None:
    page1 = Mock()
    page1.status_code = 200
    page1.text = (
        f'<a href="{_BASE}/2025/precos-gasolina-etanol-01.csv/view">x</a>'
        f'<a href="{_BASE}/2025?b_start:int=20">Próximo</a>'
    )
    page2 = Mock()
    page2.status_code = 200
    page2.text = (
        f'<a href="{_BASE}/2025/precos-gasolina-etanol-08.csv/view">x</a>'
        f'<a href="{_BASE}/2025?b_start:int=0">Anterior</a>'
    )
    with patch("bedrock.fetch.anp_ethanol.http_get_with_retry", side_effect=[page1, page2]) as get:
        found = discover_month_urls(2025, pacing_sec=0)
    assert sorted(found) == [1, 8]
    assert get.call_count == 2
    assert get.call_args_list[1].args[0].endswith("/2025?b_start:int=20")
