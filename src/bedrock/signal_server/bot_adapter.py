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
HORIZON_DEFAULTS: dict[str, dict[str, Any]] = {
    "SCALP": {
        "expiry_candles": 24,
        "confirmation_candle_limit": 6,
        "horizon_config": {
            "name": "SCALP",
            "tf": "M5",
            "stop_atr_mult": 1.5,
            "tp_atr_mult": 2.5,
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


def _adapt_one(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Transformer én bedrock-signals-entry til bot-format.

    Returnerer None hvis entry ikke er publishable eller setup mangler.
    """
    if not entry.get("published"):
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
            sig = _adapt_one(raw)
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
                "max_total_open": 6,
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
