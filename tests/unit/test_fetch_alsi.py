# pyright: reportArgumentType=false
"""Tester for ALSI EU LNG-terminal storage fetcher (sub-fase 12.10 follow-up Spor C, session 136)."""

from __future__ import annotations

from datetime import date

import pytest

from bedrock.data.schemas import ALSI_STORAGE_COLS
from bedrock.fetch.alsi import (
    AlsiFetchError,
    _gwh_to_twh,
    _normalize_record,
    _to_float_or_none,
    fetch_alsi_country_range,
    fetch_alsi_storage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_to_float_or_none_str() -> None:
    assert _to_float_or_none("32.88") == 32.88


def test_to_float_or_none_invalid() -> None:
    assert _to_float_or_none("abc") is None


def test_to_float_or_none_none() -> None:
    assert _to_float_or_none(None) is None


def test_gwh_to_twh() -> None:
    assert _gwh_to_twh(32884.97) == pytest.approx(32.88497)
    assert _gwh_to_twh(None) is None


# ---------------------------------------------------------------------------
# _normalize_record
# ---------------------------------------------------------------------------


def test_normalize_record_full() -> None:
    rec = {
        "gasDayStart": "2026-04-30",
        "inventory": {"lng": "4935.61", "gwh": "32884.97"},
        "dtmi": {"lng": "9321.97", "gwh": "62110.4"},
        "sendOut": "4355.4",
        "dtrs": "7917",
    }
    out = _normalize_record(rec, "EU")
    assert out is not None
    assert out["country"] == "eu"
    assert out["gas_day_start"] == "2026-04-30"
    assert out["inventory_twh"] == pytest.approx(32.88497)
    assert out["dtmi_twh"] == pytest.approx(62.1104)
    assert out["full_pct"] == pytest.approx(52.946, abs=0.01)
    assert out["send_out_twh"] == pytest.approx(4.3554)
    assert out["dtrs_twh"] == pytest.approx(7.917)


def test_normalize_record_full_pct_computed_when_dtmi_zero() -> None:
    rec = {
        "gasDayStart": "2026-04-30",
        "inventory": {"gwh": "100"},
        "dtmi": {"gwh": "0"},
    }
    out = _normalize_record(rec, "eu")
    assert out is not None
    assert out["full_pct"] is None


def test_normalize_record_missing_gas_day() -> None:
    assert _normalize_record({"inventory": {"gwh": "100"}}, "eu") is None


def test_normalize_record_partial_inventory() -> None:
    """Bare inventory — dtmi/sendOut mangler. Pdrev null-toleranse."""
    rec = {"gasDayStart": "2026-04-30", "inventory": {"gwh": "100"}}
    out = _normalize_record(rec, "eu")
    assert out is not None
    assert out["inventory_twh"] == 0.1
    assert out["dtmi_twh"] is None
    assert out["full_pct"] is None
    assert out["send_out_twh"] is None


# ---------------------------------------------------------------------------
# fetch_alsi_country_range — pre-parsed JSON
# ---------------------------------------------------------------------------


def test_fetch_country_range_with_raw_response() -> None:
    payload = {
        "data": [
            {
                "gasDayStart": "2026-04-30",
                "inventory": {"gwh": "32884.97"},
                "dtmi": {"gwh": "62110.4"},
                "sendOut": "4355.4",
                "dtrs": "7917",
            },
            {
                "gasDayStart": "2026-04-29",
                "inventory": {"gwh": "32627.20"},
                "dtmi": {"gwh": "62110.4"},
                "sendOut": "4406.6",
                "dtrs": "7917",
            },
        ]
    }
    df = fetch_alsi_country_range(
        "eu",
        "fake-key",
        from_date=date(2026, 4, 29),
        to_date=date(2026, 4, 30),
        raw_response=payload,
    )
    assert len(df) == 2
    assert list(df.columns) == list(ALSI_STORAGE_COLS)
    assert df["country"].iloc[0] == "eu"
    assert df["full_pct"].iloc[0] == pytest.approx(52.946, abs=0.01)


def test_fetch_country_range_empty_data() -> None:
    df = fetch_alsi_country_range(
        "eu",
        "fake-key",
        from_date=date(2026, 4, 29),
        to_date=date(2026, 4, 30),
        raw_response={"data": []},
    )
    assert df.empty
    assert list(df.columns) == list(ALSI_STORAGE_COLS)


def test_fetch_country_range_invalid_payload_type() -> None:
    with pytest.raises(AlsiFetchError, match="expected JSON object"):
        fetch_alsi_country_range(
            "eu",
            "fake-key",
            from_date=date(2026, 4, 29),
            to_date=date(2026, 4, 30),
            raw_response=["not-a-dict"],
        )


def test_fetch_country_range_invalid_data_type() -> None:
    with pytest.raises(AlsiFetchError, match="must be list"):
        fetch_alsi_country_range(
            "eu",
            "fake-key",
            from_date=date(2026, 4, 29),
            to_date=date(2026, 4, 30),
            raw_response={"data": "not-a-list"},
        )


def test_fetch_country_range_skips_non_dict_records() -> None:
    payload = {
        "data": [
            "garbage",
            {"gasDayStart": "2026-04-30", "inventory": {"gwh": "100"}},
        ]
    }
    df = fetch_alsi_country_range(
        "eu",
        "fake-key",
        from_date=date(2026, 4, 29),
        to_date=date(2026, 4, 30),
        raw_response=payload,
    )
    assert len(df) == 1


# ---------------------------------------------------------------------------
# fetch_alsi_storage orchestrator
# ---------------------------------------------------------------------------


def test_fetch_storage_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGSI_API_KEY", raising=False)
    monkeypatch.setattr("bedrock.fetch.alsi.get_secret", lambda _: None)
    with pytest.raises(AlsiFetchError, match="api_key missing"):
        fetch_alsi_storage()


def test_fetch_storage_combines_countries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub fetch_alsi_country_range og verifiser at orchestrator kombinerer
    flere countries til én DataFrame uten å gjøre HTTP."""
    import pandas as pd

    calls: list[str] = []

    def _stub(country: str, api_key: str, *, from_date, to_date, timeout=30.0, raw_response=None):
        calls.append(country)
        return pd.DataFrame(
            {
                "country": [country],
                "gas_day_start": ["2026-04-30"],
                "inventory_twh": [10.0],
                "dtmi_twh": [20.0],
                "full_pct": [50.0],
                "send_out_twh": [1.0],
                "dtrs_twh": [2.0],
            }
        )

    monkeypatch.setattr("bedrock.fetch.alsi.fetch_alsi_country_range", _stub)
    df = fetch_alsi_storage(
        countries=("eu", "de"),
        api_key="fake-key",
        pacing_sec=0.0,
    )
    assert calls == ["eu", "de"]
    assert len(df) == 2


def test_fetch_storage_skips_failed_countries(monkeypatch: pytest.MonkeyPatch) -> None:
    import pandas as pd

    def _stub(country: str, api_key: str, *, from_date, to_date, timeout=30.0, raw_response=None):
        if country == "fr":
            raise AlsiFetchError("fr 500")
        return pd.DataFrame(
            {
                "country": [country],
                "gas_day_start": ["2026-04-30"],
                "inventory_twh": [10.0],
                "dtmi_twh": [20.0],
                "full_pct": [50.0],
                "send_out_twh": [1.0],
                "dtrs_twh": [2.0],
            }
        )

    monkeypatch.setattr("bedrock.fetch.alsi.fetch_alsi_country_range", _stub)
    df = fetch_alsi_storage(
        countries=("eu", "fr", "de"),
        api_key="fake-key",
        pacing_sec=0.0,
    )
    # FR feiler, EU+DE leverer.
    assert sorted(df["country"].tolist()) == ["de", "eu"]


def test_fetch_storage_empty_when_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def _stub(country, api_key, **kw):
        raise AlsiFetchError("any")

    monkeypatch.setattr("bedrock.fetch.alsi.fetch_alsi_country_range", _stub)
    df = fetch_alsi_storage(
        countries=("eu", "de"),
        api_key="fake-key",
        pacing_sec=0.0,
    )
    assert df.empty
    assert list(df.columns) == list(ALSI_STORAGE_COLS)
