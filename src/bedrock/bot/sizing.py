"""Position-sizing — risk-% til volum.

Portert fra `~/scalp_edge/trading_bot.py` session 43 + 44 per
migrasjons-plan (`docs/migration/bot_refactor.md § 3.3 + 8 punkt 4-5`).

- Session 43: `get_risk_pct()` (ren funksjon, ingen state).
- Session 44: `compute_desired_lots()` (lot-tier + VIX/agri-nedskalering)
  og `lots_to_volume_units()` (step-volume-rounding) splittet ut fra
  `_execute_trade` og `volume_to_lots()` fra `_volume_to_lots`. Alle
  rene funksjoner for testbarhet.
"""

from __future__ import annotations

from typing import Any, Optional

from bedrock.bot.config import RiskPctConfig
from bedrock.bot.instruments import AGRI_INSTRUMENTS


def get_risk_pct(
    sig: dict[str, Any],
    global_state: dict[str, Any],
    rules: dict[str, Any],
    cfg: RiskPctConfig,
) -> float:
    """Returner risk-% for dette signalet basert på markedsregime.

    Portert fra `ScalpEdgeBot._get_risk_pct` (trading_bot.py:1734-1744).
    Null logikk-endring — kun at defaults leses fra `RiskPctConfig`
    i stedet for `rules.get("risk_pct_*", ...)` med hardkodede fallback.

    Reglene (prioriteringsrekkefølge):
    - geo aktiv ELLER character="C" ELLER vix="extreme" → quarter
    - vix="elevated" ELLER character="B" ELLER utenfor session → half
    - ellers → full

    Merk: `rules.get("risk_pct_*", ...)` respekteres fortsatt slik at
    per-instrument YAML-overrides fungerer. `cfg` gir prosess-nivå
    default.
    """
    geo = global_state.get("geo_active", False)
    vix = global_state.get("vix_regime", "normal")
    char_c = sig.get("character") == "C"
    outside = sig.get("_outside_session", False)

    if geo or char_c or vix == "extreme":
        return rules.get("risk_pct_quarter", cfg.quarter)
    if vix == "elevated" or sig.get("character") == "B" or outside:
        return rules.get("risk_pct_half", cfg.half)
    return rules.get("risk_pct_full", cfg.full)


# ─────────────────────────────────────────────────────────────
# Lot-tier + volum-konvertering
# ─────────────────────────────────────────────────────────────


def compute_desired_lots(sig: dict[str, Any], risk_pct: float) -> float:
    """Beregn ønsket lot-størrelse før stepVolume-avrunding.

    Portert fra `_execute_trade` (trading_bot.py:1551-1569). Bruker
    `horizon_config.sizing_base_risk_usd` for base-tier, så VIX/geo-
    nedskalering via `risk_pct`, så agri-halvering. Minimum 0.01 lot.

    Reglene:
    - base_risk ≥ 60 → 0.03 (MAKRO)
    - base_risk ≥ 40 → 0.02 (SWING)
    - ellers        → 0.01 (SCALP)
    - risk_pct < 0.5 → ×0.5 (gulv 0.01)
    - risk_pct < 1.0 → ×0.75 (gulv 0.01)
    - agri-instrument → ×0.5 (gulv 0.01)
    """
    hcfg = sig.get("horizon_config") or {}
    base_risk = hcfg.get("sizing_base_risk_usd", 20)
    if base_risk >= 60:
        lots = 0.03
    elif base_risk >= 40:
        lots = 0.02
    else:
        lots = 0.01

    if risk_pct < 0.5:
        lots = max(lots * 0.5, 0.01)
    elif risk_pct < 1.0:
        lots = max(lots * 0.75, 0.01)

    if sig.get("instrument", "") in AGRI_INSTRUMENTS:
        lots = max(lots * 0.5, 0.01)

    return lots


def lots_to_volume_units(
    desired_lots: float, symbol_info: Optional[dict[str, Any]]
) -> int:
    """Konverter lots til cTrader API-enheter med stepVolume-rounding.

    Portert fra `_execute_trade` (trading_bot.py:1572-1585). Hvis
    `symbol_info` mangler (kan skje hvis _on_symbol_by_id ikke har
    returnert enda): fallback 1000 enheter — matcher gammel bot.
    """
    if not symbol_info:
        return 1000
    lot_size = symbol_info["lot_size"]
    min_volume = symbol_info["min_volume"]
    step_volume = symbol_info["step_volume"]
    raw = int(desired_lots * lot_size)
    raw = max(raw, min_volume)
    if step_volume > 0:
        raw = (raw // step_volume) * step_volume
    return max(raw, step_volume if step_volume > 0 else min_volume)


def volume_to_lots(
    volume: int, symbol_info: Optional[dict[str, Any]]
) -> Optional[float]:
    """Invers av `lots_to_volume_units` — brukes for trade-logging.

    Portert fra `_volume_to_lots` (trading_bot.py:1837-1845). Returnerer
    None hvis volume er 0/None; FX-standard fallback (100 000 enheter =
    1 lot) hvis symbol_info mangler.
    """
    if not volume:
        return None
    if symbol_info and symbol_info.get("lot_size"):
        return round(volume / symbol_info["lot_size"], 2)
    return round(volume / 100000, 2)
