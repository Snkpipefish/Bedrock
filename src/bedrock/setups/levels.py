# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false
# pandas-stubs false-positives — se data/store.py for kontekst.

"""Nivå-detektor — finner støtte/motstand-nivåer i pris-historikk.

Per PLAN § 5.1. Session 16 implementerer tre detektorer:

- `detect_swing_levels`: fraktal swing-high/low på N-candle-vindu
- `detect_prior_period_levels`: ukentlig/dagsvis/månedlig H/L
- `detect_round_numbers`: psykologiske runde tall rundt nåpris

Hver detektor returnerer en **råliste** `list[Level]` uten clustering.
Merge av overlappende nivåer (swing + round number innenfor samme ATR-
bufferet) hører til setup-bygger i session 17.

Volume-profile POC/VAH/VAL og prior COT-pivot-detektorer er utsatt
(krever tick-data / mer design). ATR-bånd er kun buffer, ikke eget nivå.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Modeller
# ---------------------------------------------------------------------------


class LevelType(str, Enum):
    """Kategori for et pris-nivå. `str`-backed for YAML/JSON-vennlighet."""

    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"
    PRIOR_HIGH = "prior_high"
    PRIOR_LOW = "prior_low"
    ROUND_NUMBER = "round_number"


class Level(BaseModel):
    """Et pris-nivå (støtte eller motstand).

    - `price`: den absolutte pris-verdien
    - `type`: hvilken detektor produserte det (for traceability + scoring)
    - `strength`: normalisert 0..1; detektorer velger heuristikken —
      se hver `detect_*`-funksjon for eksakt formel
    - `ts`: tidsstempelet nivået ble formet (swing-bar, periode-end).
      `None` for round numbers (ikke tidsbundet)
    """

    price: float
    type: LevelType
    strength: float = Field(ge=0.0, le=1.0)
    ts: datetime | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Swing-detektor (fraktal N-candle)
# ---------------------------------------------------------------------------


def detect_swing_levels(ohlc: pd.DataFrame, window: int = 5) -> list[Level]:
    """Fraktal swing-high/swing-low deteksjon.

    En bar ved indeks `i` er en **swing high** hvis `ohlc.high.iloc[i]`
    er strengt større enn max-high i `[i-window, i-1]` og `[i+1, i+window]`.
    Tilsvarende for swing low med `ohlc.low`.

    **Strength-heuristikk (prominens):**

        neighbor_max = max-high blant nabo-barer (window på hver side)
        prominence   = (swing_price - neighbor_max) / swing_price
        strength     = min(1.0, 0.5 + prominence × 20)

    Tolking av formelen:

    - 2% prominens → strength ≈ 0.9 (svingen stikker markert over naboene)
    - 0.5% prominens → strength ≈ 0.6 (svak, kan være støy)
    - 0% (akkurat så vidt) → strength = 0.5 (floor for gyldige swings)

    Formelen vil raffineres i senere session med *test-count* (hvor mange
    ganger prisen har kommet tilbake og bounced) og *alder* — PLAN § 5.1
    beskriver dette. For nå er prominens den beste tilgjengelige signalen.

    Returnerer rå liste (ingen dedup). Fraktal-algoritmen kan produsere
    to nabo-swings hvis begge er lokalt max på hver sin side av en plateau;
    clustering tas i setup-bygger (session 17).

    Params:
        ohlc: DataFrame med kolonner `high`, `low` (ts som DatetimeIndex)
        window: antall bars på hver side som svingen må dominere

    Returnerer tom liste hvis `len(ohlc) < 2 × window + 1`.
    """
    if "high" not in ohlc.columns or "low" not in ohlc.columns:
        raise ValueError(
            f"detect_swing_levels: ohlc must have 'high' and 'low'. Got: {sorted(ohlc.columns)}"
        )

    n = len(ohlc)
    if n < 2 * window + 1:
        return []

    highs = ohlc["high"].to_numpy()
    lows = ohlc["low"].to_numpy()
    timestamps = ohlc.index
    levels: list[Level] = []

    for i in range(window, n - window):
        # Swing high: strengt større enn alle naboer
        left_max = highs[i - window : i].max()
        right_max = highs[i + 1 : i + window + 1].max()
        neighbor_max = max(left_max, right_max)
        if highs[i] > neighbor_max:
            prominence = (highs[i] - neighbor_max) / highs[i]
            strength = min(1.0, 0.5 + prominence * 20)
            levels.append(
                Level(
                    price=float(highs[i]),
                    type=LevelType.SWING_HIGH,
                    strength=strength,
                    ts=_to_datetime(timestamps[i]),
                )
            )

        # Swing low: strengt mindre enn alle naboer
        left_min = lows[i - window : i].min()
        right_min = lows[i + 1 : i + window + 1].min()
        neighbor_min = min(left_min, right_min)
        if lows[i] < neighbor_min:
            prominence = (neighbor_min - lows[i]) / lows[i]
            strength = min(1.0, 0.5 + prominence * 20)
            levels.append(
                Level(
                    price=float(lows[i]),
                    type=LevelType.SWING_LOW,
                    strength=strength,
                    ts=_to_datetime(timestamps[i]),
                )
            )

    return levels


# ---------------------------------------------------------------------------
# Prior weekly/daily/monthly H/L
# ---------------------------------------------------------------------------


def detect_prior_period_levels(
    ohlc: pd.DataFrame,
    period: Literal["W", "D", "M"],
) -> list[Level]:
    """Høy/lav-nivåer for hver komplette periode i historikken.

    Resampler OHLC på gitt periode ("W"=ukentlig, "D"=daglig, "M"=månedlig)
    og returnerer en `Level` for hver periodes max-high og min-low.

    **Strength-heuristikk (konstant):**

        strength = 0.8

    Disse nivåene har inherent institusjonell vekt — prior-week-high er
    universelt observert uavhengig av hvor mange ganger prisen har
    testet det. PLAN § 5.1 klassifiserer dem som "Kjent institusjonelt
    nivå". Aldersdegradering kan raffinere senere, men for MVP er 0.8
    konstant.

    Siste (potensielt inkomplette) periode inkluderes ikke automatisk —
    pandas-resample inkluderer den, men vi dropper siste rad for å unngå
    "current week's high"-rot. Hvis bruker vil ha gjeldende periode kan
    det eksponeres som parameter senere.

    Params:
        ohlc: DataFrame med `high`, `low` (DatetimeIndex påkrevd)
        period: "W" (uke, ender søndag), "D" (dag), "M" (måned-slutt)

    Raises:
        ValueError: hvis ohlc-indeksen ikke er en DatetimeIndex.
    """
    if not isinstance(ohlc.index, pd.DatetimeIndex):
        raise ValueError(
            "detect_prior_period_levels: ohlc must have DatetimeIndex. "
            f"Got: {type(ohlc.index).__name__}"
        )
    if "high" not in ohlc.columns or "low" not in ohlc.columns:
        raise ValueError(
            f"detect_prior_period_levels: ohlc must have 'high' and 'low'. "
            f"Got: {sorted(ohlc.columns)}"
        )

    # "M" er deprecated i pandas 2.2+; oversetter til "ME" (month end)
    pandas_period = "ME" if period == "M" else period

    agg = ohlc.resample(pandas_period).agg({"high": "max", "low": "min"}).dropna()

    # Drop siste periode — antas inkomplett (se docstring)
    if len(agg) <= 1:
        return []
    agg = agg.iloc[:-1]

    levels: list[Level] = []
    for ts, row in agg.iterrows():
        levels.append(
            Level(
                price=float(row["high"]),
                type=LevelType.PRIOR_HIGH,
                strength=0.8,
                ts=_to_datetime(ts),
            )
        )
        levels.append(
            Level(
                price=float(row["low"]),
                type=LevelType.PRIOR_LOW,
                strength=0.8,
                ts=_to_datetime(ts),
            )
        )

    return levels


# ---------------------------------------------------------------------------
# Round numbers (psykologiske nivåer)
# ---------------------------------------------------------------------------


def detect_round_numbers(
    current_price: float,
    step: float,
    count_above: int = 3,
    count_below: int = 3,
) -> list[Level]:
    """Psykologiske runde tall ved multipler av `step` rundt `current_price`.

    Eksempel: `current_price=2003.5`, `step=10.0`, `count_above=3`,
    `count_below=3` gir nivåer ved 2010/2020/2030 over og 2000/1990/1980
    under.

    **Strength-heuristikk (trailing-zero i step-enheter):**

        n = round(price / step)            # antall steps prisen ligger på
        z = antall trailing-zeros i n       # "hvor rund" er n?
        strength = min(0.9, 0.5 + 0.2 × z)

    Tolking:

    - z=0 (f.eks. price=2010, step=10 → n=201) → strength 0.5 (minst rund)
    - z=1 (f.eks. price=2050, step=10 → n=205) → strength 0.7 (medium)
    - z=2+ (f.eks. price=2000, step=10 → n=200) → strength 0.9 (mest rund)

    Heuristikken reflekterer hvordan tradere faktisk prisetter runde tall:
    $2000 tiltrekker mer ordre-flyt enn $2010. Step-param tilpasser
    granularitet per instrument (1.0 for JPY-kryss, 0.01 for EURUSD, 10.0
    for Gold, etc.). Instrument-tilpasset step hører i Fase 5 config.

    Returnerer rå liste — ingen clustering mot evt. swings ved samme
    pris-nivå (hører i setup-bygger, session 17).

    Params:
        current_price: nåværende pris-nivå; levels genereres over/under
        step: avstand mellom runde tall (instrument-spesifikk)
        count_above/count_below: hvor mange nivåer i hver retning

    Raises:
        ValueError: hvis `step <= 0`.
    """
    if step <= 0:
        raise ValueError(f"detect_round_numbers: step must be > 0, got {step}")

    levels: list[Level] = []

    # Nærmeste runde over (strengt over current_price)
    import math

    nearest_above = math.ceil(current_price / step) * step
    if nearest_above <= current_price:
        nearest_above += step
    for i in range(count_above):
        price = nearest_above + i * step
        levels.append(
            Level(
                price=price,
                type=LevelType.ROUND_NUMBER,
                strength=_round_number_strength(price, step),
                ts=None,
            )
        )

    # Nærmeste runde under (strengt under current_price)
    nearest_below = math.floor(current_price / step) * step
    if nearest_below >= current_price:
        nearest_below -= step
    for i in range(count_below):
        price = nearest_below - i * step
        levels.append(
            Level(
                price=price,
                type=LevelType.ROUND_NUMBER,
                strength=_round_number_strength(price, step),
                ts=None,
            )
        )

    return levels


def _round_number_strength(price: float, step: float) -> float:
    """Beregn strength basert på antall trailing-zeros i (price/step)."""
    n = round(price / step)
    if n == 0:
        # Spesialtilfelle: price == 0. Stryk ned for å unngå uendelig zeros.
        return 0.5
    n = abs(n)
    zeros = 0
    while n % 10 == 0 and n > 0:
        n //= 10
        zeros += 1
    return min(0.9, 0.5 + 0.2 * zeros)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def rank_levels(levels: list[Level]) -> list[Level]:
    """Sorter nivå-liste synkende på `strength`.

    Ingen dedup eller merging — rå sortering. Nivå-clustering hører i
    setup-bygger (session 17) når vi vet hvilken ATR-buffer som gjelder
    for instrumentet.

    Stabil sortering: ved lik strength bevares detektorens rekkefølge.
    """
    return sorted(levels, key=lambda lvl: lvl.strength, reverse=True)


# ---------------------------------------------------------------------------
# Interne helpers
# ---------------------------------------------------------------------------


def _to_datetime(ts: object) -> datetime | None:
    """Konverter pandas Timestamp (eller annet) til stdlib datetime."""
    if ts is None:
        return None
    if isinstance(ts, pd.Timestamp):
        return ts.to_pydatetime()
    if isinstance(ts, datetime):
        return ts
    # Fallback: prøv pandas
    return pd.Timestamp(ts).to_pydatetime()
