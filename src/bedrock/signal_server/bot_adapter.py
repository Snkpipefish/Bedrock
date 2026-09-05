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

Batch-ferskhet / TTL (session 2026-09-05): boten skal bruke top-level
``signals_generated_at`` (tidspunktet ``signals-all`` sist kjørte, lest
fra sidecar ``signals_bot.json.last_run.json``) som grunnlag for TTL —
altså *batch*-staleness, ikke per-signal ``created_at``. ``created_at``
speiler ``setup.first_seen`` som nullstilles ved hver fil-skriving, og
ga tidligere at stabile SWING-setups utløp etter 4t selv om batchen var
fersk. ``generated_at`` er fortsatt HTTP-responstidspunktet og sier
ingenting om datagrunnlaget.

Ordre-type og TP: alle horisonter sendes som MARKET-ordre, og ordren
bærer full TP (``t1``) server-side. cTrader lukker dermed 100 % av
posisjonen ved T1 uten at boten trenger å være online; botens
partial-close-sti (delvis lukking ved T1 + trailing på resten) er kun
fallback hvis server-TP ikke ble satt.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_VERSION = "2.1"

# Per-horisont default-konfig portert fra scalp_edge signal_server-præsedens.
# expiry_candles telles av boten i *lukkede M15-candles* (exit.py P5a-
# timeout, entry.py:_on_candle_closed) — ikke M5 slik scalp_edge gjorde:
# SCALP=24 (6t; hard close ved 48 = 12t), SWING=96 (24t), MAKRO=336 (84t
# = 3.5 dager). Kun SCALP har tids-exit; SWING/MAKRO holdes til trail/
# SL/T1 og bruker expiry kun som watchlist-utløp.
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

# Entry-zone-bredde: halv-bredde = ZONE_ATR_FRACTION × ATR, men aldri mer
# enn ZONE_SL_FRACTION × |entry − SL|. Se `_entry_zone_from_setup`.
ZONE_ATR_FRACTION = 0.25
ZONE_SL_FRACTION = 0.4
ZONE_FALLBACK_BPS = 5.0  # halv-bredde i bps av entry når ATR mangler/<=0


def _normalize_horizon(horizon: str) -> str:
    """Bedrock bruker `makro`/`swing`/`scalp` (lowercase) i signals_bot.json;
    bot venter UPPERCASE."""
    return horizon.strip().upper()


def _positive_float(value: Any) -> float | None:
    """Tolk `value` som positivt tall; None hvis mangler/ugyldig/<=0."""
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def _entry_zone_from_setup(setup: dict[str, Any]) -> list[float]:
    """Bot venter `entry_zone: [low, high]` rundt entry. Bedrocks setup
    har ett `entry`-tall + `atr` + `sl`.

    Halv-bredde = ZONE_ATR_FRACTION × ATR (fallback ZONE_FALLBACK_BPS av
    entry når ATR mangler), men aldri mer enn ZONE_SL_FRACTION × |entry −
    SL| når SL er et positivt tall. Uten SL-cappen kunne SCALP-setups med
    SL 0.01–0.15 ATR unna få en zone bredere enn hele SL-avstanden, slik
    at en fill i zone-kanten lå praktisk talt på (eller forbi) stoppen.
    Med cappen på 0.4 etterlater verste fill i zone-kanten 60 % av den
    planlagte SL-avstanden; boten håndhever i tillegg en fill-time-guard
    mot SL-avstand ved faktisk ordreinnlegging.
    """
    inner = setup.get("setup", setup)
    entry = float(inner.get("entry") or 0.0)
    atr = float(inner.get("atr") or 0.0)
    if entry <= 0:
        return [0.0, 0.0]
    half = atr * ZONE_ATR_FRACTION if atr > 0 else entry * ZONE_FALLBACK_BPS / 10_000
    sl = _positive_float(inner.get("sl"))
    if sl is not None:
        # sl == entry er degenerert (risiko 0) — sonen kollapser til
        # punktet; `_adapt_one` dropper slike entries uansett.
        half = min(half, ZONE_SL_FRACTION * abs(entry - sl))
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

    # Drop entries uten gyldig SL: bot ville sendt MARKET-ordre + amend
    # stop_loss=0.0, som lar posisjonen stå ubeskyttet på cTrader-server.
    # Observert 2026-05-06: 4 orphan-posisjoner uten SL fra session 142
    # INCLUDE_UNPUBLISHED-vinduet hvor sl=None slapp gjennom som stop=0.0.
    if stop is None or float(stop) <= 0:
        log.warning(
            "[ADAPTER] %s %s %s — sl=%r mangler/<=0; entry droppet for å "
            "hindre ubeskyttet posisjon på server.",
            instrument,
            horizon,
            direction,
            stop,
        )
        return None

    # Stop på entry = risiko 0: kan ikke sizes eller handles.
    if abs(float(inner.get("entry") or 0.0) - float(stop)) <= 0.0:
        log.warning(
            "[ADAPTER] %s %s %s — stop == entry (%r); entry droppet (risiko 0).",
            instrument,
            horizon,
            direction,
            stop,
        )
        return None

    correlation_group = ASSET_CLASS_TO_GROUP.get(asset_class, "fx")

    return {
        "id": setup_id,
        "instrument": instrument,
        "direction": direction,
        "horizon": horizon,
        "status": "watchlist",
        "entry_zone": entry_zone,
        "alert_level": float(inner.get("entry") or 0.0),
        "stop": float(stop),
        "t1": float(t1) if t1 is not None else 0.0,
        "atr": float(inner.get("atr") or 0.0),
        "expiry_candles": defaults["expiry_candles"],
        "confirmation_candle_limit": defaults["confirmation_candle_limit"],
        "horizon_config": defaults["horizon_config"],
        "correlation_group": correlation_group,
        "created_at": created_at,
        # Bedrock-spesifikke felt — bot ignorerer ukjente, men beholdes for trace.
        # max_score + publish_floor (session 2026-06-12): trengs for å
        # normalisere score på tvers av horisonter i R-multiple-analyse —
        # grade viste seg ikke-prediktiv, så fremtidig gating skal
        # kalibreres på score-margin (krever at loggen fanger skalaen).
        "score": entry.get("score"),
        "max_score": entry.get("max_score"),
        "publish_floor": entry.get("min_score_publish"),
        "grade": entry.get("grade"),
        "rr": inner.get("rr"),
    }


def default_global_state() -> dict[str, Any]:
    """Fail-open `global_state`: ingen geo-risiko, normal VIX, standard
    korrelasjonsgrenser og ingen blackouts.

    Brukes både som adapter-default og som fallback når
    `bedrock.signal_server.global_state.build_global_state` ikke kan
    kjøre (DB mangler o.l.). Returnerer alltid en fersk dict.
    """
    return {
        "geo_risk_active": False,
        # Boten leser `geo_active` (entry.py/sizing.py); `geo_risk_active`
        # beholdes for scalp_edge-kompatibilitet. Samme verdi i begge.
        "geo_active": False,
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
        "event_blackout": {},
        "usda_blackout": {},
    }


def adapt_to_bot_format(
    bedrock_signals: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    valid_until_minutes: int = 60,
    global_state: dict[str, Any] | None = None,
    rules: dict[str, Any] | None = None,
    include_unpublished: bool = False,
    source_generated_at: str | None = None,
) -> dict[str, Any]:
    """Transformer bedrocks signals_bot.json (flat list) til bot-payload.

    Args:
        bedrock_signals: liste av bedrock-signal-entries (signals_bot.json).
        now: brukes for valid_until + created_at-fallback. Default = utc.
        valid_until_minutes: hvor lenge signal-batch-en er gyldig.
            Bot polling-intervall er typisk 60s; default 60min holder
            flere refresh-intervaller.
        global_state: optional dict med geo_risk_active / vix_regime /
            event_blackout etc. Default: `default_global_state()`.
        rules: optional dict med stop_multiplier / etc. Default: bot's
            interne defaults brukes hvis ikke satt.
        include_unpublished: hvis True, inkluder også entries med
            published=False i bot-batchen. Brukes på demo-konto for å
            la boten teste hele setup-utvalget. Default False (kun
            publishable entries går til bot på live-konto).
        source_generated_at: ISO-8601-UTC-tidspunkt for når signal-
            batchen (signals_bot.json) sist ble generert. Legges i
            payload som `signals_generated_at` (null hvis ukjent) og er
            botens TTL-grunnlag — se modul-docstring.

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
        global_state = default_global_state()
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
        # HTTP-responstidspunkt. Sier ingenting om datagrunnlagets alder.
        "generated_at": now.isoformat(),
        # Batch-ferskhet: når signals-all sist kjørte. Botens TTL-grunnlag.
        "signals_generated_at": source_generated_at,
    }
