"""Instrument-lookup-konstanter for trading-bot.

Portert 1:1 fra `~/scalp_edge/trading_bot.py:146-232 + 256-298` per Fase 8
(`docs/migration/bot_refactor.md § 3.5 + 5.3`). Disse er rene data-lookup-
tabeller som ikke endrer seg uten kode-deploy, så de bor her i stedet for
i YAML (YAML-en ville blitt ren støy og kreve Pydantic-modellering).

Asset-gruppe-parametre (`GROUP_PARAMS`) og session-tider (`AGRI_SESSION`)
flyttes til `config/bot.yaml` via `bot.config` — de er terskler brukeren
justerer. Denne modulen inneholder kun mapping-data.
"""

from __future__ import annotations

from typing import Optional

# ─────────────────────────────────────────────────────────────
# Trading-symbol-mapping: Bedrock-navn → kandidat-tickere hos broker
# ─────────────────────────────────────────────────────────────

INSTRUMENT_MAP: dict[str, list[str]] = {
    # FX
    "EURUSD": ["EURUSD"],
    "USDJPY": ["USDJPY"],
    "GBPUSD": ["GBPUSD"],
    "AUDUSD": ["AUDUSD"],
    # Metals + energy + indices
    "GOLD": ["XAUUSD", "GOLD"],
    "SILVER": ["XAGUSD", "SILVER"],
    "OIL BRENT": ["XBRUSD", "OIL BRENT", "UKOIL"],
    "OIL WTI": ["XTIUSD", "OIL WTI", "USOIL"],
    "SPX500": ["SPX500"],
    "US100": ["US100"],
    # Soft commodities
    "Corn": ["Corn"],
    "Wheat": ["Wheat"],
    "Soybean": ["Soybean"],
    "Coffee": ["Coffee"],
    "Cotton": ["Cotton"],
    "Sugar": ["Sugar"],
    "Cocoa": ["Cocoa"],
}

# Rene pris-feed-symboler (abonneres på spot, handles ikke)
PRICE_FEED_MAP: dict[str, list[str]] = {
    "USDCHF": ["USDCHF"],
    "USDCAD": ["USDCAD"],
    "USDNOK": ["USDNOK"],
    "NZDUSD": ["NZDUSD"],
    "EURGBP": ["EURGBP"],
    "NatGas": ["Natural Gas", "US Natural Gas", "XNG", "NATGAS", "NGAS"],
    "BTC": ["BTC", "BTCUSD", "Bitcoin"],
    "ETH": ["ETH", "ETHUSD", "Ethereum"],
    "SOL": ["SOL", "SOLUSD", "Solana"],
    "XRP": ["XRP", "XRPUSD", "Ripple"],
    "ADA": ["ADA", "ADAUSD", "Cardano"],
    "DOGE": ["DOGE", "DOGEUSD", "Dogecoin"],
}

# Mapping fra trading-instrument (signal-navn) → prices-fil-nøkkel
INSTRUMENT_TO_PRICE_KEY: dict[str, str] = {
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD",
    "GOLD": "Gold",
    "SILVER": "Silver",
    "OIL BRENT": "Brent",
    "OIL WTI": "WTI",
    "SPX500": "SPX",
    "US100": "NAS100",
    "Corn": "Corn",
    "Wheat": "Wheat",
    "Soybean": "Soybean",
    "Coffee": "Coffee",
    "Cotton": "Cotton",
    "Sugar": "Sugar",
    "Cocoa": "Cocoa",
}

# ─────────────────────────────────────────────────────────────
# FX USD-retning: "long" = long USD ved BUY, "short" = short USD ved BUY.
# Brukes for å detektere motstridende posisjoner (f.eks. EURUSD short +
# GBPUSD long).
# ─────────────────────────────────────────────────────────────

FX_USD_DIRECTION: dict[str, str] = {
    "EURUSD": "short",  # BUY EURUSD = short USD
    "GBPUSD": "short",
    "AUDUSD": "short",
    "NZDUSD": "short",
    "USDJPY": "long",  # BUY USDJPY = long USD
    "USDCHF": "long",
    "USDCAD": "long",
    "USDNOK": "long",
}

# ─────────────────────────────────────────────────────────────
# Agri-grupperinger
# ─────────────────────────────────────────────────────────────

AGRI_INSTRUMENTS: frozenset[str] = frozenset(
    {"Corn", "Wheat", "Soybean", "Coffee", "Cotton", "Sugar", "Cocoa"}
)

# Sub-grupper: mais/soya/hvete korrelerer .85+, kaffe/sukker/kakao
# er softs-kluster
AGRI_SUBGROUPS: dict[str, str] = {
    "Corn": "grains",
    "Wheat": "grains",
    "Soybean": "grains",
    "Coffee": "softs",
    "Sugar": "softs",
    "Cocoa": "softs",
    "Cotton": "cotton",
}

# ─────────────────────────────────────────────────────────────
# Instrument → intern gruppe (for GROUP_PARAMS-oppslag i bot.yaml)
# ─────────────────────────────────────────────────────────────

INSTRUMENT_GROUP: dict[str, str] = {
    "EURUSD": "fx",
    "USDJPY": "fx",
    "GBPUSD": "fx",
    "AUDUSD": "fx",
    "GOLD": "gold",
    "SILVER": "silver",  # ikke korrelert nok til å blokkere hverandre
    "OIL BRENT": "oil",
    "OIL WTI": "oil",
    "SPX500": "indices",
    "US100": "indices",
    # Agri — egne grupper per instrument, blokkerer ikke hverandre
    "Corn": "corn",
    "Wheat": "wheat",
    "Soybean": "soybean",
    "Coffee": "coffee",
    "Cocoa": "cocoa",
    "Sugar": "sugar",
    "Cotton": "cotton",
}

# Default-gruppe hvis instrument ikke i tabellen
DEFAULT_GROUP = "fx"


# ─────────────────────────────────────────────────────────────
# Helpers (portert fra trading_bot.py:233-253)
# ─────────────────────────────────────────────────────────────


def net_usd_direction(instrument: str, direction: str) -> Optional[str]:
    """Returner 'long_usd' eller 'short_usd' for ett FX-par+retning, ellers None.

    `direction` er "buy" eller "sell" (signal-side).
    """
    usd_dir = FX_USD_DIRECTION.get(instrument)
    if usd_dir is None:
        return None
    # usd_dir er effekt av BUY. Ved SELL flippes.
    if direction == "buy":
        return f"{usd_dir}_usd"
    if direction == "sell":
        flipped = "short" if usd_dir == "long" else "long"
        return f"{flipped}_usd"
    return None


def looks_like_fx_pair(instrument: str) -> bool:
    """True hvis instrument-navnet ser ut som et FX-par.

    Fanger XXXUSD og USDXXX-navngivning; ekskluderer åpenbart ikke-FX
    (metaller/energi/indekser som også kan ha USD i ticker).
    """
    if not instrument:
        return False
    NON_FX_PREFIXES = {
        "GOLD",
        "SILVER",
        "XAU",
        "XAG",
        "OIL",
        "XBR",
        "XTI",
        "SPX",
        "NAS",
        "US30",
        "US100",
        "DAX",
        "VIX",
        "DXY",
    }
    if any(instrument.startswith(p) for p in NON_FX_PREFIXES):
        return False
    return "USD" in instrument and 5 <= len(instrument) <= 7


def get_group_name(instrument: str) -> str:
    """Returner gruppe-navn for et instrument ('fx', 'gold', 'corn', ...).

    Ukjente instrumenter → DEFAULT_GROUP ('fx'), slik at bot ikke
    krasjer på første ukjente symbol.
    """
    return INSTRUMENT_GROUP.get(instrument, DEFAULT_GROUP)
