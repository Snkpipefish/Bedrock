"""Instrument-lookup-konstantene må matche scalp_edge 1:1.

Siden dette er rene data-lookup-tabeller er det liten vits i logiske
tester; vi sjekker at de viktigste entries finnes og at helpers
oppfører seg som før.
"""

from __future__ import annotations

from bedrock.bot.instruments import (
    AGRI_INSTRUMENTS,
    AGRI_SUBGROUPS,
    DEFAULT_GROUP,
    FX_USD_DIRECTION,
    INSTRUMENT_GROUP,
    INSTRUMENT_MAP,
    INSTRUMENT_TO_PRICE_KEY,
    PRICE_FEED_MAP,
    get_group_name,
    looks_like_fx_pair,
    net_usd_direction,
)


def test_instrument_map_has_core_symbols() -> None:
    for core in ("EURUSD", "GOLD", "Corn", "Coffee", "OIL BRENT"):
        assert core in INSTRUMENT_MAP
        assert len(INSTRUMENT_MAP[core]) >= 1  # minst én ticker-kandidat


def test_price_feed_map_excludes_trading_symbols() -> None:
    # Pris-feed-symboler skal ikke dobles med trading-symboler
    overlap = set(PRICE_FEED_MAP) & set(INSTRUMENT_MAP)
    assert overlap == set(), f"overlapp: {overlap}"


def test_instrument_to_price_key_covers_trading_symbols() -> None:
    # Alle trading-symboler må ha en prices-fil-nøkkel
    missing = set(INSTRUMENT_MAP) - set(INSTRUMENT_TO_PRICE_KEY)
    assert missing == set(), f"mangler price-key: {missing}"


def test_agri_subgroups_match_agri_instruments() -> None:
    assert set(AGRI_SUBGROUPS) == set(AGRI_INSTRUMENTS)


def test_instrument_group_has_all_trading_symbols() -> None:
    missing = set(INSTRUMENT_MAP) - set(INSTRUMENT_GROUP)
    assert missing == set(), f"mangler gruppe: {missing}"


def test_get_group_name_unknown_falls_back() -> None:
    assert get_group_name("WHATEVER") == DEFAULT_GROUP
    assert get_group_name("") == DEFAULT_GROUP


def test_get_group_name_known() -> None:
    assert get_group_name("EURUSD") == "fx"
    assert get_group_name("GOLD") == "gold"
    assert get_group_name("Corn") == "corn"


def test_net_usd_direction_eurusd_buy_is_short_usd() -> None:
    # BUY EURUSD betyr long EUR / short USD
    assert net_usd_direction("EURUSD", "buy") == "short_usd"


def test_net_usd_direction_eurusd_sell_is_long_usd() -> None:
    assert net_usd_direction("EURUSD", "sell") == "long_usd"


def test_net_usd_direction_usdjpy_buy_is_long_usd() -> None:
    assert net_usd_direction("USDJPY", "buy") == "long_usd"


def test_net_usd_direction_usdjpy_sell_is_short_usd() -> None:
    assert net_usd_direction("USDJPY", "sell") == "short_usd"


def test_net_usd_direction_non_fx_returns_none() -> None:
    assert net_usd_direction("GOLD", "buy") is None
    assert net_usd_direction("Corn", "sell") is None


def test_net_usd_direction_unknown_direction_returns_none() -> None:
    assert net_usd_direction("EURUSD", "hold") is None


def test_looks_like_fx_pair_positive() -> None:
    for s in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF"):
        assert looks_like_fx_pair(s), s


def test_looks_like_fx_pair_negative() -> None:
    # Non-FX med USD i ticker må fanges
    for s in ("GOLD", "SILVER", "OIL BRENT", "SPX500", "US100", "XAUUSD"):
        assert not looks_like_fx_pair(s), s
    # Tom streng + noe helt annet
    assert not looks_like_fx_pair("")
    assert not looks_like_fx_pair("BTC")


def test_fx_usd_direction_covers_all_fx_in_instrument_map() -> None:
    # Hvert FX-par i INSTRUMENT_MAP må ha en USD-retning
    fx_in_map = [s for s in INSTRUMENT_MAP if looks_like_fx_pair(s)]
    missing = set(fx_in_map) - set(FX_USD_DIRECTION)
    assert missing == set(), f"mangler USD-retning: {missing}"
