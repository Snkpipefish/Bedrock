"""Position-sizing — risk-% til volum.

Portert fra `~/scalp_edge/trading_bot.py:1734-1744` session 43 per
migrasjons-plan (`docs/migration/bot_refactor.md § 3.3 + 8 punkt 4`).

Scope i session 43: `get_risk_pct()` (ren funksjon, ingen state).
`size_volume()` (lot-tier + step-volume-konvertering) ligger i
`_execute_trade` i gammel bot og portes i session 44 sammen med
selve ordre-sendingen — de deler lot/volume-state fra CtraderClient
og er tett koblet til cTrader-protokollen.
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
