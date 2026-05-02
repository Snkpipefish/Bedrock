"""Tester for bedrock.fetch.treasury_auctions (Spor F6)."""

from __future__ import annotations

from unittest.mock import Mock

import pandas as pd
import pytest

from bedrock.fetch.treasury_auctions import (
    TreasuryFetchError,
    _normalize_treasury_rows,
    fetch_treasury_auctions,
)

SAMPLE_ROWS = [
    {
        "cusip": "912797TD9",
        "auctionDate": "2026-05-05T00:00:00",
        "issueDate": "2026-05-07T00:00:00",
        "securityType": "Bill",
        "securityTerm": "6-Week",
        "bidToCoverRatio": "2.92",
        "indirectBidderAccepted": "50300000000",
        "primaryDealerAccepted": "20300000000",
        "offeringAmount": "75000000000",
        "totalAccepted": "72300000000",
    },
    {
        "cusip": "91282CXX0",
        "auctionDate": "2026-05-08T00:00:00",
        "issueDate": "2026-05-15T00:00:00",
        "securityType": "Note",
        "securityTerm": "10-Year",
        "bidToCoverRatio": "2.45",
        "indirectBidderAccepted": "30000000000",
        "primaryDealerAccepted": "8000000000",
        "offeringAmount": "39000000000",
        "totalAccepted": "39000000000",
    },
]


def test_normalize_returns_bedrock_schema() -> None:
    df = _normalize_treasury_rows(SAMPLE_ROWS)
    assert list(df.columns) == [
        "auction_date",
        "security_type",
        "security_term",
        "cusip",
        "bid_to_cover_ratio",
        "indirect_pct",
        "primary_dealer_pct",
        "offering_amount",
        "total_accepted",
    ]
    assert len(df) == 2
    assert df["auction_date"].iloc[0] == "2026-05-05"
    assert df["security_type"].iloc[0] == "Bill"
    assert df["security_term"].iloc[0] == "6-Week"
    assert df["bid_to_cover_ratio"].iloc[0] == pytest.approx(2.92)
    # indirect_pct = 50.3B / 72.3B
    assert df["indirect_pct"].iloc[0] == pytest.approx(50300000000 / 72300000000, rel=1e-4)


def test_normalize_skips_missing_required_fields() -> None:
    rows = [
        {"cusip": "X", "securityType": "Bill"},  # missing auctionDate, securityTerm
        SAMPLE_ROWS[0],
    ]
    df = _normalize_treasury_rows(rows)
    assert len(df) == 1
    assert df["cusip"].iloc[0] == "912797TD9"


def test_normalize_handles_empty_total_accepted() -> None:
    rows = [
        {
            "cusip": "X",
            "auctionDate": "2026-01-01T00:00:00",
            "securityType": "Bill",
            "securityTerm": "6-Week",
            "bidToCoverRatio": "2.5",
            "indirectBidderAccepted": "100",
            "primaryDealerAccepted": "50",
            "totalAccepted": None,
            "offeringAmount": "200",
        }
    ]
    df = _normalize_treasury_rows(rows)
    assert len(df) == 1
    assert pd.isna(df["indirect_pct"].iloc[0])
    assert pd.isna(df["primary_dealer_pct"].iloc[0])


def test_fetch_treasury_auctions_via_raw_response() -> None:
    df = fetch_treasury_auctions(raw_response=SAMPLE_ROWS)
    assert len(df) == 2
    assert df["security_type"].tolist() == ["Bill", "Note"]


def test_fetch_treasury_auctions_http_error_raises() -> None:
    from unittest.mock import patch

    fake = Mock()
    fake.status_code = 500
    fake.text = "boom"
    with patch("bedrock.fetch.treasury_auctions.http_get_with_retry", return_value=fake):
        with pytest.raises(TreasuryFetchError):
            fetch_treasury_auctions()


def test_fetch_treasury_auctions_non_list_payload_raises() -> None:
    with pytest.raises(TreasuryFetchError):
        fetch_treasury_auctions(raw_response={"not": "a list"})
