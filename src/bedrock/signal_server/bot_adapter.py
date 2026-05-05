"""Adapter: bedrocks signals_bot.json → bedrock-bot signal-payload-format.

Sub-fase 12.9 D1a (PLAN § 21 / docs/bedrock_bot_cutover.md). Bedrock-bot
(`src/bedrock/bot/`) venter wrapped object med `{schema_version, signals[],
valid_until, global_state, rules}` per scalp_edge-presedens. Bedrocks
``signals_bot.json`` er flat list med score/grade/setup/families/analog
per entry. Denne adapteren bygger broen.

Mapping per felt er dokumentert i `docs/bedrock_bot_cutover.md` § D1a.

Bruk:

```python
from bedrock.signal_server.bot_adapter import adapt_to_bot_format
import json

with open("data/signals_bot.json") as f:
    bedrock_signals = json.load(f)
payload = adapt_to_bot_format(bedrock_signals)
```

Bot-output er ``schema_version="2.1"`` slik at bedrock-bot's
``SUPPORTED_SCHEMA_VERSIONS = {"1.0", "2.0", "2.1"}`` aksepterer det
uten warning.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_VERSION = "2.1"

# Per-horisont default-konfig portert fra scalp_edge signal_server-præsedens.
# expiry_candles bruker M5-candles per scalp_edge-konvensjon: SCALP=24
# (2t), SWING=96 (8t), MAKRO=336 (28t = ~6 trading days).
#
# `sizing_base_risk_usd` styrer base-lot per horisont via
# `bedrock.bot.sizing.compute_desired_lots`:
#   ≥60 → 0.03 lot (MAKRO)
#   ≥40 → 0.02 lot (SWING)
#   <40 → 0.01 lot (SCALP)
# Manglende felt = default 20 = SCALP-tier; settes derfor eksplisitt
# her per horisont (sub-fase 12.9 D5+ fix). Verdiene matcher scalp_edge-
# convention fra trading_bot.py:1551-1569.
# Per-horisont × per-gruppe trailing-stop-multipliers.
#
# `exit_trail_atr_mult[<group>]` overstyrer `group_params.trail_atr` i bot.yaml.
# `_resolve_trail_mult` i exit.py:529 leter etter denne nøkkelen først, faller
# tilbake til rules.trail_atr_multiplier og deretter group_params.
#
# Designprinsipp:
# - SCALP bruker M15-ATR → moderat responsiv trail (~2.5–3.5×).
# - SWING bruker H1-ATR → tåler 1H-støy, gir rom for normale pullbacks (~3.5–5.0×).
# - MAKRO bruker H1-ATR → multi-uke-tese, må overleve hele D1-pullbacks
#   (~5.0–7.0× ≈ 1.2–1.5×ATR-D1).
#
# Per gruppe er multiplikatorene tunet etter typisk realisert volatilitet:
# - Mer volatile assets (natgas, crypto, oil, edelmetaller) får bredere trail.
# - FX/indeks får tightere trail (mindre absolutte støy-bevegelser).
# - Agri (grains/softs) får mid-range — USDA-events skaper reaksjons-svinger
#   som tett trail klipper ut feil.
TRAIL_MULT_BY_HORIZON_GROUP: dict[str, dict[str, float]] = {
    "SCALP": {
        "fx": 2.5,
        "indices": 2.5,
        "gold": 3.0,
        "silver": 3.0,
        "platinum": 3.0,
        "copper": 3.0,
        "oil": 3.0,
        "natgas": 3.5,
        "crypto": 3.5,
        "corn": 2.5,
        "wheat": 2.5,
        "soybean": 2.5,
        "coffee": 2.5,
        "cocoa": 2.5,
        "sugar": 2.5,
        "cotton": 2.5,
    },
    "SWING": {
        "fx": 3.5,
        "indices": 3.5,
        "gold": 4.0,
        "silver": 4.5,
        "platinum": 4.0,
        "copper": 4.0,
        "oil": 4.0,
        "natgas": 4.5,
        "crypto": 5.0,
        "corn": 3.5,
        "wheat": 3.5,
        "soybean": 3.5,
        "coffee": 3.5,
        "cocoa": 3.5,
        "sugar": 3.5,
        "cotton": 3.5,
    },
    "MAKRO": {
        "fx": 5.0,
        "indices": 5.0,
        "gold": 6.0,
        "silver": 6.5,
        "platinum": 6.0,
        "copper": 5.5,
        "oil": 6.0,
        "natgas": 7.0,
        "crypto": 7.0,
        "corn": 5.0,
        "wheat": 5.0,
        "soybean": 5.0,
        "coffee": 5.0,
        "cocoa": 5.0,
        "sugar": 5.0,
        "cotton": 5.0,
    },
}


HORIZON_DEFAULTS: dict[str, dict[str, Any]] = {
    "SCALP": {
        "expiry_candles": 24,
        "confirmation_candle_limit": 6,
        "horizon_config": {
            "name": "SCALP",
            "tf": "M5",
            "stop_atr_mult": 1.5,
            "tp_atr_mult": 2.5,
            "sizing_base_risk_usd": 20,
            "exit_trail_atr_mult": TRAIL_MULT_BY_HORIZON_GROUP["SCALP"],
            # SCALP: MARKET — fart > entry-kvalitet på korte tidsskalaer.
            # SL-laget (~few hundred ms) er kjent kostnad, akseptert.
            "use_limit_orders": False,
        },
    },
    "SWING": {
        "expiry_candles": 96,
        "confirmation_candle_limit": 12,
        "horizon_config": {
            "name": "SWING",
            "tf": "M15",
            "stop_atr_mult": 2.0,
            "tp_atr_mult": 3.5,
            "sizing_base_risk_usd": 40,
            "exit_trail_atr_mult": TRAIL_MULT_BY_HORIZON_GROUP["SWING"],
            # SWING: MARKET — entry kun etter bekreftet confirmation-candle
            # (15m close med body+wick+EMA-bias riktig vei). LIMIT på
            # alert_level ble fylt selv om markedet etterpå drev mot oss
            # — confirmation gir bedre retnings-bevis enn rene zone-touches.
            "use_limit_orders": False,
        },
    },
    "MAKRO": {
        "expiry_candles": 336,
        "confirmation_candle_limit": 24,
        "horizon_config": {
            "name": "MAKRO",
            "tf": "H1",
            "stop_atr_mult": 3.0,
            "tp_atr_mult": None,  # MAKRO bruker trailing-only per Fase 4
            "sizing_base_risk_usd": 60,
            "exit_trail_atr_mult": TRAIL_MULT_BY_HORIZON_GROUP["MAKRO"],
            # MAKRO: MARKET — samme begrunnelse som SWING. Multi-uke tese
            # krever at vi tar entry kun når retnings-konfirmasjon er
            # tydelig på lukket candle, ikke ved ren zone-berøring.
            "use_limit_orders": False,
        },
    },
}

# asset_class → correlation_group-mapping (mer granulær enn
# bot/instruments.py:INSTRUMENT_GROUP, men kompatibel for korrelasjons-
# grenser per scalp_edge-presedens).
ASSET_CLASS_TO_GROUP: dict[str, str] = {
    "fx": "fx",
    "metals": "metals",
    "energy": "energy",
    "indices": "indices",
    "crypto": "crypto",
    "grains": "grains",
    "softs": "softs",
}


def _normalize_horizon(horizon: str) -> str:
    """Bedrock bruker `makro`/`swing`/`scalp` (lowercase) i signals_bot.json;
    bot venter UPPERCASE."""
    return horizon.strip().upper()


def _entry_zone_from_setup(setup: dict[str, Any]) -> list[float]:
    """Bot venter `entry_zone: [low, high]` for limit-zone. Bedrocks
    setup har ett `entry`-tall + `atr`. Lager zone som ±0.25*atr rundt
    entry (smal cluster — bot's confirm-logic tar over derfra).
    """
    inner = setup.get("setup", setup)
    entry = float(inner.get("entry") or 0.0)
    atr = float(inner.get("atr") or 0.0)
    if entry <= 0:
        return [0.0, 0.0]
    half = atr * 0.25 if atr > 0 else entry * 0.0005  # fallback: 5 bps
    return [entry - half, entry + half]


def _adapt_one(
    entry: dict[str, Any], *, include_unpublished: bool = False
) -> dict[str, Any] | None:
    """Transformer én bedrock-signals-entry til bot-format.

    Returnerer None hvis setup mangler. Hvis include_unpublished=False
    (default) filtreres entries med published=false ut. På demo-konto
    ønsker vi ofte alle setups for testing; sett include_unpublished=True
    via /bot/signals?include_unpublished=1 eller via ServerConfig.
    """
    if not include_unpublished and not entry.get("published"):
        return None

    setup_outer = entry.get("setup") or {}
    if not setup_outer:
        return None
    inner = setup_outer.get("setup") or {}
    if not inner:
        return None

    instrument = entry.get("instrument") or ""
    horizon_raw = entry.get("horizon") or "SWING"
    horizon = _normalize_horizon(horizon_raw)
    direction = entry.get("direction") or "buy"
    asset_class = entry.get("asset_class") or "fx"

    defaults = HORIZON_DEFAULTS.get(horizon, HORIZON_DEFAULTS["SWING"])

    setup_id = setup_outer.get("setup_id") or f"{instrument}_{direction}_{horizon}"
    created_at = setup_outer.get("first_seen") or datetime.now(timezone.utc).isoformat()

    entry_zone = _entry_zone_from_setup(setup_outer)
    stop = inner.get("sl")
    t1 = inner.get("tp")  # None for MAKRO trailing-only — bot håndterer

    correlation_group = ASSET_CLASS_TO_GROUP.get(asset_class, "fx")

    return {
        "id": setup_id,
        "instrument": instrument,
        "direction": direction,
        "horizon": horizon,
        "status": "watchlist",
        "entry_zone": entry_zone,
        "alert_level": float(inner.get("entry") or 0.0),
        "stop": float(stop) if stop is not None else 0.0,
        "t1": float(t1) if t1 is not None else 0.0,
        "atr": float(inner.get("atr") or 0.0),
        "expiry_candles": defaults["expiry_candles"],
        "confirmation_candle_limit": defaults["confirmation_candle_limit"],
        "horizon_config": defaults["horizon_config"],
        "correlation_group": correlation_group,
        "created_at": created_at,
        # Bedrock-spesifikke felt — bot ignorerer ukjente, men beholdes for trace
        "score": entry.get("score"),
        "grade": entry.get("grade"),
        "rr": inner.get("rr"),
    }


def adapt_to_bot_format(
    bedrock_signals: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    valid_until_minutes: int = 60,
    global_state: dict[str, Any] | None = None,
    rules: dict[str, Any] | None = None,
    include_unpublished: bool = False,
) -> dict[str, Any]:
    """Transformer bedrocks signals_bot.json (flat list) til bot-payload.

    Args:
        bedrock_signals: liste av bedrock-signal-entries (signals_bot.json).
        now: brukes for valid_until + created_at-fallback. Default = utc.
        valid_until_minutes: hvor lenge signal-batch-en er gyldig.
            Bot polling-intervall er typisk 60s; default 60min holder
            flere refresh-intervaller.
        global_state: optional dict med geo_risk_active / vix_regime / etc.
            Default: konservativ no-risk, normal-vix.
        rules: optional dict med stop_multiplier / etc. Default: bot's
            interne defaults brukes hvis ikke satt.
        include_unpublished: hvis True, inkluder også entries med
            published=False i bot-batchen. Brukes på demo-konto for å
            la boten teste hele setup-utvalget. Default False (kun
            publishable entries går til bot på live-konto).

    Returns:
        Wrapped payload som bedrock-bot's comms.py forventer.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    adapted: list[dict[str, Any]] = []
    for raw in bedrock_signals:
        if not isinstance(raw, dict):
            continue
        try:
            sig = _adapt_one(raw, include_unpublished=include_unpublished)
        except (KeyError, ValueError, TypeError) as exc:
            log.warning(
                "[ADAPTER] skip entry %s/%s: %s",
                raw.get("instrument"),
                raw.get("horizon"),
                exc,
            )
            continue
        if sig is not None:
            adapted.append(sig)

    valid_until = (now + timedelta(minutes=valid_until_minutes)).isoformat()

    if global_state is None:
        global_state = {
            "geo_risk_active": False,
            "vix_regime": "normal",
            "correlation_config": {
                "max_per_group": 2,
                # Bot leser nøkkelen `max_total` (entry.py:1182). Tidligere
                # `max_total_open` traff ikke — bot brukte default 6. I
                # test-fasen ønsker vi mer breddet (3 horisonter × 22
                # instrumenter = stort signal-univers); 20 lar ~7 instr
                # være aktive samtidig på tvers av horisonter.
                "max_total": 20,
            },
        }
    if rules is None:
        rules = {
            "stop_multiplier": 3.0,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "signals": adapted,
        "valid_until": valid_until,
        "global_state": global_state,
        "rules": rules,
        "n_total": len(bedrock_signals),
        "n_published": len(adapted),
        "generated_at": now.isoformat(),
    }
