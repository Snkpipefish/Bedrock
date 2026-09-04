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

from typing import Any

from bedrock.bot.config import RiskPctConfig


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
    - geo aktiv ELLER grade="C" ELLER vix="extreme" → quarter
    - vix="elevated" ELLER grade="B" ELLER utenfor session → half
    - ellers (grade A/A+) → full

    Merk: `rules.get("risk_pct_*", ...)` respekteres fortsatt slik at
    per-instrument YAML-overrides fungerer. `cfg` gir prosess-nivå
    default.

    Feltnavn-historikk: scalp_edge-bot brukte "character"; bedrock
    signal_server bruker "grade" (A+/A/B/C i schema v2.x). Vi leser
    "grade" her — eldre "character"-baserte signal-payloads vil falle
    gjennom til full risk (sig.get returnerer None).
    """
    geo = global_state.get("geo_active", False)
    vix = global_state.get("vix_regime", "normal")
    grade = sig.get("grade")
    outside = sig.get("_outside_session", False)

    if geo or grade == "C" or vix == "extreme":
        return rules.get("risk_pct_quarter", cfg.quarter)
    if vix == "elevated" or grade == "B" or outside:
        return rules.get("risk_pct_half", cfg.half)
    return rules.get("risk_pct_full", cfg.full)


# ─────────────────────────────────────────────────────────────
# Lot-tier + volum-konvertering
# ─────────────────────────────────────────────────────────────


def compute_risk_lots(
    *,
    risk_amount: float,
    sl_distance: float,
    symbol_info: dict[str, Any] | None,
    quote_to_account: float,
    min_lot_max_overshoot: float = 1.5,
) -> tuple[int, float, str | None]:
    """Risikobasert volum: tap ved SL ≈ `risk_amount` (kontovaluta).

    Erstatter faste lot-tiers (0.01/0.02/0.03 per horisont, session
    2026-09-04). Live-data viste at faste lots ga 3–550 NOK per R
    avhengig av instrument (NATGAS min-lot = 1.0 lot dominerte all
    PnL), og at «Risk=… (x%)» i loggen var kosmetisk.

        lots = risk_amount / (sl_distance × enheter_per_lot × quote→konto)

    cTrader-volum er i 1/100 enheter: `lot_size` er cents-enheter per
    lot, så enheter_per_lot = lot_size / 100. PnL per lot per 1.0
    prisbevegelse i quote-valuta = enheter_per_lot; `quote_to_account`
    konverterer til kontovaluta (USD→NOK ≈ 8-10, JPY→NOK via USDJPY).

    Returnerer (volume_units, lots, blokk-årsak). Volum rundes NED til
    `step_volume`. Under `min_volume`: aksepteres hvis min-lot-risiko
    ≤ `min_lot_max_overshoot` × risk_amount, ellers blokkeres traden
    (bedre å hoppe over enn å risikere flere ganger planlagt).
    """
    if not symbol_info or not symbol_info.get("lot_size"):
        return 0, 0.0, "symbol_info/lot_size mangler"
    lot_size = int(symbol_info["lot_size"])
    step = int(symbol_info.get("step_volume") or 0) or lot_size
    min_vol = int(symbol_info.get("min_volume") or 0) or step
    max_vol = int(symbol_info.get("max_volume") or 0)
    if risk_amount <= 0 or sl_distance <= 0 or quote_to_account <= 0:
        return (
            0,
            0.0,
            (
                f"ugyldig input (risk={risk_amount:.2f} sl={sl_distance:.5f} kurs={quote_to_account:.4f})"
            ),
        )
    units_per_lot = lot_size / 100.0
    risk_per_lot = sl_distance * units_per_lot * quote_to_account
    raw_volume = (risk_amount / risk_per_lot) * lot_size
    volume = int(raw_volume // step) * step
    if volume < min_vol:
        min_risk = (min_vol / 100.0) * sl_distance * quote_to_account
        if min_risk > risk_amount * min_lot_max_overshoot:
            return (
                0,
                0.0,
                (
                    f"min-lot risikerer {min_risk:.0f} > {min_lot_max_overshoot:.1f}× "
                    f"planlagt {risk_amount:.0f}"
                ),
            )
        volume = min_vol
    if max_vol and volume > max_vol:
        volume = int(max_vol // step) * step
    return volume, round(volume / lot_size, 4), None


def lots_to_volume_units(desired_lots: float, symbol_info: dict[str, Any] | None) -> int:
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


def volume_to_lots(volume: int, symbol_info: dict[str, Any] | None) -> float | None:
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
