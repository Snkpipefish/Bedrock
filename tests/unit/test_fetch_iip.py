# pyright: reportArgumentType=false
"""Tester for IIP REMIT supply-unavailability fetcher (sub-fase 12.10 follow-up Spor C, session 136)."""

from __future__ import annotations

import pytest

from bedrock.data.schemas import IIP_REMIT_COLS
from bedrock.fetch.iip import (
    IipFetchError,
    _capacity_gwhd,
    _normalize_record,
    fetch_iip_page,
    fetch_iip_remit,
)

# ---------------------------------------------------------------------------
# _capacity_gwhd
# ---------------------------------------------------------------------------


def test_capacity_gwhd_with_unit() -> None:
    assert _capacity_gwhd({"capacity": "304.8", "unit": "GWh/d"}) == 304.8


def test_capacity_gwhd_no_unit() -> None:
    """Tomme units er OK — REMIT-konvensjon er GWh/d."""
    assert _capacity_gwhd({"capacity": "100", "unit": ""}) == 100.0


def test_capacity_gwhd_unknown_unit_returns_none() -> None:
    """Vi normaliserer ikke MW/MWh — sjeldent i praksis."""
    assert _capacity_gwhd({"capacity": "100", "unit": "MW"}) is None


def test_capacity_gwhd_not_dict() -> None:
    assert _capacity_gwhd("not-a-dict") is None
    assert _capacity_gwhd(None) is None


# ---------------------------------------------------------------------------
# _normalize_record
# ---------------------------------------------------------------------------


SAMPLE_UMM = {
    "submitted": "2026-05-02 05:02:15",
    "published": "2026-05-02 05:13:24",
    "from": "2026-06-16 04:00:00",
    "to": "2026-06-27 04:00:00",
    "status": "Active",
    "message": {
        "messageId": "ABC123",
        "messageType": "Gas treatment plant unavailability",
        "unavailabilityType": "Planned",
    },
    "unavailable": {"capacity": "304.8", "unit": "GWh/d"},
    "available": {"capacity": "192.0", "unit": "GWh/d"},
    "technical": {"capacity": "496.8", "unit": "GWh/d"},
    "balancingZone": [
        {"code": "21YNL----TTF---1", "name": "Dutch TTF"},
    ],
    "direction": "Exit",
    "asset": {"code": "21W0000000000087", "name": "UGS Bergermeer"},
    "unavailabilityReason": "maintenance",
}


def test_normalize_record_full() -> None:
    out = _normalize_record(SAMPLE_UMM)
    assert out is not None
    assert out["message_id"] == "ABC123"
    assert out["published_ts"] == "2026-05-02 05:13:24"
    assert out["event_from_ts"] == "2026-06-16 04:00:00"
    assert out["status"] == "Active"
    assert out["message_type"] == "Gas treatment plant unavailability"
    assert out["unavailability_type"] == "Planned"
    assert out["unavailable_capacity_gwhd"] == 304.8
    assert out["balancing_zone_code"] == "21YNL----TTF---1"
    assert out["balancing_zone_name"] == "Dutch TTF"
    assert out["direction"] == "Exit"
    assert out["asset_code"] == "21W0000000000087"


def test_normalize_record_missing_message_id_returns_none() -> None:
    bad = {**SAMPLE_UMM, "message": {"messageType": "X"}}
    assert _normalize_record(bad) is None


def test_normalize_record_empty_balancing_zone() -> None:
    rec = {**SAMPLE_UMM, "balancingZone": []}
    out = _normalize_record(rec)
    assert out is not None
    assert out["balancing_zone_code"] is None


def test_normalize_record_missing_optional_capacities() -> None:
    rec = {
        "message": {"messageId": "X"},
        "published": "2026-05-02 05:00:00",
    }
    out = _normalize_record(rec)
    assert out is not None
    assert out["message_id"] == "X"
    assert out["unavailable_capacity_gwhd"] is None
    assert out["balancing_zone_code"] is None


# ---------------------------------------------------------------------------
# fetch_iip_page — pre-parsed JSON
# ---------------------------------------------------------------------------


def test_fetch_page_with_raw_response() -> None:
    payload = {
        "last_page": 213,
        "total": 50,
        "data": [SAMPLE_UMM],
    }
    df, lp = fetch_iip_page(1, "fake-key", raw_response=payload)
    assert len(df) == 1
    assert list(df.columns) == list(IIP_REMIT_COLS)
    assert lp == 213
    assert df["message_id"].iloc[0] == "ABC123"


def test_fetch_page_invalid_payload_type() -> None:
    with pytest.raises(IipFetchError, match="expected JSON object"):
        fetch_iip_page(1, "fake-key", raw_response="garbage")


def test_fetch_page_invalid_data_type() -> None:
    with pytest.raises(IipFetchError, match="must be list"):
        fetch_iip_page(1, "fake-key", raw_response={"data": "not-a-list"})


def test_fetch_page_skips_non_dict_records() -> None:
    payload = {"data": ["garbage", SAMPLE_UMM, None], "last_page": 1}
    df, _ = fetch_iip_page(1, "fake-key", raw_response=payload)
    assert len(df) == 1


def test_fetch_page_default_last_page_when_missing() -> None:
    payload = {"data": []}
    df, lp = fetch_iip_page(1, "fake-key", raw_response=payload)
    assert df.empty
    assert lp == 1


# ---------------------------------------------------------------------------
# fetch_iip_remit orchestrator
# ---------------------------------------------------------------------------


def test_fetch_remit_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGSI_API_KEY", raising=False)
    monkeypatch.setattr("bedrock.fetch.iip.get_secret", lambda _: None)
    with pytest.raises(IipFetchError, match="api_key missing"):
        fetch_iip_remit()


def test_fetch_remit_max_pages_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """max_pages=1 stopper etter første side selv om last_page=10."""
    import pandas as pd

    calls: list[int] = []

    def _stub(page, api_key, *, size, timeout, raw_response=None):
        calls.append(page)
        return (
            pd.DataFrame([_normalize_record(SAMPLE_UMM)]),
            10,  # last_page=10 — orchestrator skal likevel stoppe etter 1
        )

    monkeypatch.setattr("bedrock.fetch.iip.fetch_iip_page", _stub)
    df = fetch_iip_remit(api_key="fake-key", max_pages=1, pacing_sec=0.0)
    assert calls == [1]
    assert len(df) == 1


def test_fetch_remit_walks_all_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    import pandas as pd

    calls: list[int] = []

    def _stub(page, api_key, *, size, timeout, raw_response=None):
        calls.append(page)
        # 3 sider totalt; varierende message_id per page.
        rec = {**SAMPLE_UMM, "message": {**SAMPLE_UMM["message"], "messageId": f"MSG-{page}"}}
        return pd.DataFrame([_normalize_record(rec)]), 3

    monkeypatch.setattr("bedrock.fetch.iip.fetch_iip_page", _stub)
    df = fetch_iip_remit(api_key="fake-key", pacing_sec=0.0)
    assert calls == [1, 2, 3]
    assert sorted(df["message_id"].tolist()) == ["MSG-1", "MSG-2", "MSG-3"]


def test_fetch_remit_dedup_on_message_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """API kan returnere duplikate message_id på tvers av sider; siste vinner."""
    import pandas as pd

    def _stub(page, api_key, *, size, timeout, raw_response=None):
        if page == 1:
            return pd.DataFrame([_normalize_record(SAMPLE_UMM)]), 2
        # Page 2 returnerer SAMME message_id som page 1
        rec = {**SAMPLE_UMM, "unavailable": {"capacity": "999", "unit": "GWh/d"}}
        return pd.DataFrame([_normalize_record(rec)]), 2

    monkeypatch.setattr("bedrock.fetch.iip.fetch_iip_page", _stub)
    df = fetch_iip_remit(api_key="fake-key", pacing_sec=0.0)
    assert len(df) == 1
    # "Last wins" — verdi fra page 2.
    assert df["unavailable_capacity_gwhd"].iloc[0] == 999.0


def test_fetch_remit_stop_before_published_ts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop når en page returnerer KUN meldinger publisert <= threshold (inkr.)."""
    import pandas as pd

    def _stub(page, api_key, *, size, timeout, raw_response=None):
        # Page 1: published 2026-05-02 (nyeste — sorted DESC)
        # Page 2: published 2026-04-15 (eldre)
        if page == 1:
            rec = {**SAMPLE_UMM, "published": "2026-05-02 05:00:00"}
            return pd.DataFrame([_normalize_record(rec)]), 5
        rec = {
            **SAMPLE_UMM,
            "published": "2026-04-15 12:00:00",
            "message": {**SAMPLE_UMM["message"], "messageId": "OLD"},
        }
        return pd.DataFrame([_normalize_record(rec)]), 5

    monkeypatch.setattr("bedrock.fetch.iip.fetch_iip_page", _stub)
    df = fetch_iip_remit(
        api_key="fake-key",
        pacing_sec=0.0,
        stop_before_published_ts="2026-05-01 00:00:00",
    )
    # Stop etter page 2 (alle <= threshold).
    assert len(df) == 2
    assert sorted(df["message_id"].tolist()) == ["ABC123", "OLD"]


def test_fetch_remit_handles_failed_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """En feilet side skal logges og hoppes over, ikke avbryte hele kjøringen."""
    import pandas as pd

    def _stub(page, api_key, *, size, timeout, raw_response=None):
        if page == 2:
            raise IipFetchError("page 2 down")
        return pd.DataFrame([_normalize_record(SAMPLE_UMM)]), 3

    monkeypatch.setattr("bedrock.fetch.iip.fetch_iip_page", _stub)
    df = fetch_iip_remit(api_key="fake-key", pacing_sec=0.0)
    # Pages 1 og 3 leverer; 2 hopper over. Dedup på message_id (begge har samme id).
    assert len(df) == 1


def test_fetch_remit_empty_returns_empty_df(monkeypatch: pytest.MonkeyPatch) -> None:
    import pandas as pd

    def _stub(page, api_key, *, size, timeout, raw_response=None):
        return pd.DataFrame(columns=list(IIP_REMIT_COLS)), 1

    monkeypatch.setattr("bedrock.fetch.iip.fetch_iip_page", _stub)
    df = fetch_iip_remit(api_key="fake-key", pacing_sec=0.0)
    assert df.empty
    assert list(df.columns) == list(IIP_REMIT_COLS)
