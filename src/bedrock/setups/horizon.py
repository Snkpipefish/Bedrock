"""Horisont-klassifisering + score-gate + horisont-hysterese.

Per PLAN § 5.5 + § 5.4.2. Session 19 legger til siste komponent i
setup-generatoren: fra *setup-karakteristikk* (entry_tf + expected_hold)
til horisont — ikke fra score.

Tre funksjoner:

1. `classify_horizon(entry_tf, expected_hold_days)` — rule-based
   tildeling. SCALP for intraday, SWING for dagsvis, MAKRO for ukesvis.
2. `is_score_sufficient(score, horizon, min_score_publish)` — score-
   gate (PLAN § 5.5 "Scoring-YAML har min_score_publish per horisont").
3. `apply_horizon_hysteresis(candidate, previous, score, thresholds,
   buffer_pct)` — ±5% hysterese rundt terskler slik at SWING ikke
   flip-flopper til SCALP når score svinger rundt 2.5.

Alt er rene funksjoner uten state — kombineres i Fase 5 med
instrument-YAML og snapshot-persistens for å gi stabile horisont-
tildelinger på tvers av kjøringer.
"""

from __future__ import annotations

from bedrock.setups.generator import Direction, Horizon


# ---------------------------------------------------------------------------
# Timeframe-normalisering
# ---------------------------------------------------------------------------

# Set med kjente intraday-timeframes (≤ 1 time)
_INTRADAY_TFS: frozenset[str] = frozenset(
    {"1m", "5m", "15m", "30m", "m1", "m5", "m15", "m30", "M1", "M5", "M15", "M30"}
)

# Mid-frame (over intraday, opp til daglig)
_MID_TFS: frozenset[str] = frozenset(
    {"1h", "4h", "h1", "h4", "H1", "H4", "1H", "4H"}
)

# Daglig og lengre
_DAILY_PLUS_TFS: frozenset[str] = frozenset(
    {"1d", "d", "d1", "D", "1D", "D1", "1w", "w", "w1", "W", "1W", "W1"}
)


def _is_intraday(tf: str) -> bool:
    return tf in _INTRADAY_TFS


def _is_daily_plus(tf: str) -> bool:
    return tf in _DAILY_PLUS_TFS or tf in _MID_TFS


# ---------------------------------------------------------------------------
# Hold-tid estimert fra TP-distanse
# ---------------------------------------------------------------------------


def estimate_expected_hold_days(
    entry: float,
    tp: float | None,
    atr: float,
    atr_per_day: float = 1.0,
) -> float | None:
    """Grov estimat på hvor lenge setup-et vil holdes basert på TP-distanse.

    Tommelfinger-regel: prisbevegelser på ~1 ATR per dag. Hold-tid ≈
    TP-distanse i ATR-enheter / `atr_per_day`. Parameteren `atr_per_day`
    kan kalibreres per instrument når backtest-data viser faktisk
    volatilitet.

    Returnerer `None` for MAKRO-setups (tp=None) — caller signaliserer
    "trailing, udefinert hold" og bruker MAKRO-regelen direkte.
    """
    if tp is None:
        return None
    if atr <= 0:
        return None
    atr_distance = abs(tp - entry) / atr
    return atr_distance / atr_per_day


# ---------------------------------------------------------------------------
# Rule-based klassifisering
# ---------------------------------------------------------------------------


def classify_horizon(
    entry_tf: str,
    expected_hold_days: float | None,
) -> Horizon:
    """Klassifiser horisont fra entry-TF + estimert hold-tid.

    Regler (PLAN § 5.5):

    - `expected_hold_days=None` (MAKRO-signal fra caller) → MAKRO
    - intraday-TF (≤ 30m) OG hold < 1 dag → SCALP
    - intraday-TF OG hold ≥ 1 dag → SWING (hold overstyrer TF)
    - daglig/ukesvis + hold < 7 → SCALP (kort setup på lang TF)
    - daglig/ukesvis + hold 7-21 → SWING
    - daglig/ukesvis + hold > 21 → MAKRO

    Ukjent TF behandles som daglig (konservativt).
    """
    if expected_hold_days is None:
        return Horizon.MAKRO

    if _is_intraday(entry_tf):
        if expected_hold_days < 1.0:
            return Horizon.SCALP
        # Intraday-TF + hold ≥ 1 dag: trader har brukt lav TF for timing
        # men setup-et har swing-karakter
        return Horizon.SWING

    # Daily eller lengre (eller ukjent → behandler som daglig)
    if expected_hold_days < 7.0:
        return Horizon.SCALP
    if expected_hold_days <= 21.0:
        return Horizon.SWING
    return Horizon.MAKRO


# ---------------------------------------------------------------------------
# Score-gate
# ---------------------------------------------------------------------------


def is_score_sufficient(
    score: float,
    horizon: Horizon,
    min_score_publish: dict[Horizon, float],
) -> bool:
    """Returnerer True hvis `score ≥ min_score_publish[horizon]`.

    Hvis horisonten ikke finnes i `min_score_publish` (ikke konfigurert),
    returneres True — defensivt, caller får eksplisitt sjekke
    konfigurasjonen hvis det er feil.
    """
    threshold = min_score_publish.get(horizon)
    if threshold is None:
        return True
    return score >= threshold


# ---------------------------------------------------------------------------
# Hysterese rundt horisont-terskler
# ---------------------------------------------------------------------------


def apply_horizon_hysteresis(
    candidate: Horizon,
    previous: Horizon | None,
    score: float,
    horizon_thresholds: dict[Horizon, float],
    buffer_pct: float = 0.05,
) -> Horizon:
    """Bruk ±`buffer_pct` hysterese rundt horisont-terskler.

    Per PLAN § 5.4.2: hvis score er innenfor buffer av *en hvilken som
    helst* terskel OG `previous ≠ candidate`, behold `previous`.
    Formålet er å hindre flip-flopping mellom SWING og SCALP når score
    svinger rundt terskelen (2.5 ± 0.125 = 2.375-2.625 med 5%).

    - `previous=None` → returner candidate uten hysterese (første kjøring)
    - `previous == candidate` → returner candidate uendret
    - `buffer_pct=0` → ingen hysterese (lik candidate)

    Hysteresen er symmetrisk: både oppgang (SCALP → SWING) og nedgang
    (SWING → SCALP) dempes. Dette er viktig — ellers ville horisonten
    drive jevnt oppover over tid.
    """
    if previous is None or previous == candidate:
        return candidate
    if buffer_pct <= 0:
        return candidate

    # Sjekk om score ligger innenfor buffer-sonen av noen terskel
    for threshold in horizon_thresholds.values():
        if threshold <= 0:
            continue
        buffer = threshold * buffer_pct
        if abs(score - threshold) <= buffer:
            return previous  # for nær terskel → stabil

    return candidate


__all__ = [
    "classify_horizon",
    "estimate_expected_hold_days",
    "is_score_sufficient",
    "apply_horizon_hysteresis",
]


# Ubrukt import-guard: sikrer at Direction eksporteres fra samme lag —
# nyttig for kaller-modul som tar begge enums fra samme sted.
_ = Direction
