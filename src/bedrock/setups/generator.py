"""Setup-bygger — fra nivå-liste + nåpris til asymmetrisk setup.

Per PLAN § 5.2 + § 5.3. Session 17 implementerer:

- ATR-beregning (buffer-enhet for SL, clustering og stabilitets-filtre)
- Nivå-clustering (merge swing + round number innenfor ATR-buffer)
- `build_setup(instrument, direction, horizon, current_price, atr, levels, config)`
  returnerer et `Setup`-objekt eller `None` hvis ingen valid setup kan bygges
- Asymmetri-gate per horisont (min R:R)
- MAKRO-setup får `tp=None` (trailing-only)

Determinisme + hysterese (§ 5.4) og horisont-klassifisering (§ 5.5)
kommer i senere sessions. Denne modulen er rein funksjon: samme input →
samme output, ingen state.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from bedrock.setups.levels import Level, LevelType

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Direction(str, Enum):
    """Trade-retning. `str`-backed for YAML/JSON-vennlighet."""

    BUY = "buy"
    SELL = "sell"


class Horizon(str, Enum):
    """Setup-horisont. PLAN § 5.5 bestemmer tildeling; her er den et input."""

    SCALP = "scalp"
    SWING = "swing"
    MAKRO = "makro"


# ---------------------------------------------------------------------------
# Modeller
# ---------------------------------------------------------------------------


class ClusteredLevel(BaseModel):
    """Et merget nivå: flere `Level` innenfor samme ATR-buffer.

    Representerer konfluens — f.eks. en swing-high som faller sammen med
    en round number får høyere strength enn hver isolert.

    - `price`: pris-verdien fra den sterkeste bidragsyteren i klyngen
    - `types`: distinkte `LevelType` som bidro (for explain/UI)
    - `strength`: strongest.strength + 0.1 × (source_count - 1), cap 1.0
    - `source_count`: antall `Level` som ble merget inn
    """

    price: float
    types: list[LevelType]
    strength: float = Field(ge=0.0, le=1.0)
    source_count: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class Setup(BaseModel):
    """Et ferdig setup — entry/SL/TP + kontekst.

    `tp` og `rr` er `None` for MAKRO-setups (kun trailing eksekvering;
    exit håndteres av bot når trend brytes).
    """

    instrument: str
    direction: Direction
    horizon: Horizon
    entry: float
    sl: float
    tp: float | None
    rr: float | None
    atr: float

    # Traceability til nivå-kilder
    entry_cluster_price: float
    entry_cluster_types: list[LevelType]
    tp_cluster_price: float | None
    tp_cluster_types: list[LevelType] | None

    model_config = ConfigDict(extra="forbid")


class SetupConfig(BaseModel):
    """Bygger-parametre. Overstyres per instrument i senere fase via YAML.

    Defaults matcher PLAN § 5.2-5.3:
    - `cluster_atr_multiplier=0.3`: nivåer innenfor 0.3×ATR cluster sammen
    - `sl_atr_multiplier=0.3`: SL ligger 0.3×ATR forbi entry-nivået
    - `min_entry_strength=0.6`: entry-klyngen må minst ha denne strength
    - `min_rr_scalp=1.5`, `min_rr_swing=2.5`: asymmetri-floor per horisont
    """

    cluster_atr_multiplier: float = Field(default=0.3, gt=0.0)
    sl_atr_multiplier: float = Field(default=0.3, gt=0.0)
    min_entry_strength: float = Field(default=0.6, ge=0.0, le=1.0)
    min_rr_scalp: float = Field(default=1.5, gt=0.0)
    min_rr_swing: float = Field(default=2.5, gt=0.0)

    model_config = ConfigDict(extra="forbid")

    def min_rr_for(self, horizon: Horizon) -> float | None:
        """MAKRO har ingen fast min R:R (trailing), returner None."""
        if horizon == Horizon.SCALP:
            return self.min_rr_scalp
        if horizon == Horizon.SWING:
            return self.min_rr_swing
        return None  # MAKRO


# ---------------------------------------------------------------------------
# ATR (Average True Range)
# ---------------------------------------------------------------------------


def compute_atr(ohlc: pd.DataFrame, period: int = 14) -> float:
    """Beregn ATR (Average True Range) for siste `period` bars.

    True Range pr bar:
        TR = max(high - low,
                 |high - close_prev|,
                 |low  - close_prev|)

    ATR = simple moving average av TR over `period` bars.
    (Wilder's exponential smoothing er mer vanlig i trading, men SMA er
    tilstrekkelig MVP; kan raffineres til Wilder når drivere trenger det.)

    Kaster `ValueError` hvis det ikke er nok bars (< period + 1) eller
    manglende kolonner.

    Returnerer en float (siste ATR-verdi), ikke en serie. Drivere som
    trenger historikk-ATR kan reimplementere.
    """
    required = {"high", "low", "close"}
    missing = required - set(ohlc.columns)
    if missing:
        raise ValueError(f"compute_atr: ohlc missing columns {sorted(missing)}")

    if len(ohlc) < period + 1:
        raise ValueError(
            f"compute_atr: need >= period+1 bars ({period + 1}), got {len(ohlc)}"
        )

    high = ohlc["high"]
    low = ohlc["low"]
    close_prev = ohlc["close"].shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - close_prev).abs(),
            (low - close_prev).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.rolling(window=period).mean().iloc[-1]
    return float(atr)


# ---------------------------------------------------------------------------
# Nivå-clustering
# ---------------------------------------------------------------------------


def cluster_levels(levels: list[Level], buffer: float) -> list[ClusteredLevel]:
    """Merge nivåer innenfor `buffer` pris-avstand via transitiv single-link.

    Algoritme (greedy, sortert etter pris ASC):
    1. Sorter nivåer etter pris
    2. Gå gjennom; hvis nåværende nivå ligger innenfor `buffer` av
       **forrige** nivå i klyngen, legg til. Ellers start ny klynge
    3. For hver klynge: pris = den sterkestes pris, types = distinkte,
       strength = max_strength + 0.1 × (n-1), cap 1.0

    Transitiv koblig betyr at levels ved 100.0, 100.2, 100.5 med
    buffer=0.3 alle havner i samme klynge (kjede-effekt) fordi hver
    er innenfor `buffer` av den forrige.

    Params:
        levels: rå-liste fra detektor (typisk `detect_*`-output konkatenert)
        buffer: pris-avstand; typisk `atr × cluster_atr_multiplier` fra
            `SetupConfig` (default 0.3×ATR)

    Returnerer tom liste for tom input. `buffer <= 0` → ingen merging
    (hver level blir sin egen klynge).
    """
    if not levels:
        return []

    sorted_by_price = sorted(levels, key=lambda lvl: lvl.price)

    clusters: list[list[Level]] = []
    current: list[Level] = [sorted_by_price[0]]

    for lvl in sorted_by_price[1:]:
        if buffer > 0 and (lvl.price - current[-1].price) <= buffer:
            current.append(lvl)
        else:
            clusters.append(current)
            current = [lvl]
    clusters.append(current)

    return [_merge_cluster(group) for group in clusters]


def _merge_cluster(group: list[Level]) -> ClusteredLevel:
    """Bygg en `ClusteredLevel` fra en gruppe av nærliggende `Level`.

    - price = den sterkestes pris (ikke snitt — bevarer presisjon på
      faktiske støtte/motstand-nivåer)
    - strength = strongest.strength + 0.1 × (n - 1), cap 1.0
      → konfluens-bonus (f.eks. swing + round → +0.1)
    - types = distinkte i stabil rekkefølge
    """
    strongest = max(group, key=lambda lvl: lvl.strength)
    # Stabil rekkefølge: bevar første forekomst
    seen_types: list[LevelType] = []
    for lvl in group:
        if lvl.type not in seen_types:
            seen_types.append(lvl.type)
    confluence_bonus = 0.1 * (len(group) - 1)
    strength = min(1.0, strongest.strength + confluence_bonus)

    return ClusteredLevel(
        price=float(strongest.price),
        types=seen_types,
        strength=strength,
        source_count=len(group),
    )


# ---------------------------------------------------------------------------
# Setup-bygger
# ---------------------------------------------------------------------------


def build_setup(
    instrument: str,
    direction: Direction,
    horizon: Horizon,
    current_price: float,
    atr: float,
    levels: list[Level],
    config: SetupConfig | None = None,
) -> Setup | None:
    """Bygg ett asymmetrisk setup eller returner `None` hvis umulig.

    Algoritme (deterministisk):

    1. Cluster `levels` med buffer = `config.cluster_atr_multiplier × atr`
    2. Finn **entry-klynge**: nærmeste klynge *bak* nåpris som oppfyller
       `strength ≥ min_entry_strength`. BUY = støtte under, SELL =
       motstand over. Ingen funnet → `None`
    3. **SL** = entry ± `config.sl_atr_multiplier × atr` (forbi entry-
       nivået i retning motsatt trade)
    4. **TP** per horisont:
       - **SCALP**: 1. klynge i retningen; fallback til 2. hvis 1. ikke
         gir nok R:R
       - **SWING**: 2. klynge i retningen (PLAN § 5.2); fallback til 3.
       - **MAKRO**: ingen TP, returner `Setup` med `tp=None, rr=None`
    5. **Asymmetri-gate**: R:R må være ≥ `config.min_rr_for(horizon)`.
       Hvis ingen TP-kandidat tilfredsstiller → `None`

    `atr` tas som parameter (ikke beregnet her) slik at caller kan
    gjenbruke samme verdi på tvers av flere `build_setup`-kall for samme
    instrument (en per horisont, per retning).
    """
    cfg = config if config is not None else SetupConfig()

    buffer = cfg.cluster_atr_multiplier * atr
    clusters = cluster_levels(levels, buffer)
    if not clusters:
        return None

    entry_cluster = _find_entry_cluster(clusters, current_price, direction, cfg.min_entry_strength)
    if entry_cluster is None:
        return None

    entry = entry_cluster.price
    sl = _compute_sl(entry, direction, cfg.sl_atr_multiplier * atr)

    if horizon == Horizon.MAKRO:
        # MAKRO: ingen fast TP — bot-tråling overtar. Entry + SL er nok.
        return Setup(
            instrument=instrument,
            direction=direction,
            horizon=horizon,
            entry=entry,
            sl=sl,
            tp=None,
            rr=None,
            atr=atr,
            entry_cluster_price=entry_cluster.price,
            entry_cluster_types=entry_cluster.types,
            tp_cluster_price=None,
            tp_cluster_types=None,
        )

    # SCALP/SWING: finn TP-klynge som oppfyller min R:R
    tp_result = _find_tp_cluster(
        clusters=clusters,
        current_price=current_price,
        direction=direction,
        entry=entry,
        sl=sl,
        horizon=horizon,
        min_rr=cfg.min_rr_for(horizon),
    )
    if tp_result is None:
        return None

    tp_cluster, rr = tp_result
    return Setup(
        instrument=instrument,
        direction=direction,
        horizon=horizon,
        entry=entry,
        sl=sl,
        tp=tp_cluster.price,
        rr=rr,
        atr=atr,
        entry_cluster_price=entry_cluster.price,
        entry_cluster_types=entry_cluster.types,
        tp_cluster_price=tp_cluster.price,
        tp_cluster_types=tp_cluster.types,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _find_entry_cluster(
    clusters: list[ClusteredLevel],
    current_price: float,
    direction: Direction,
    min_strength: float,
) -> ClusteredLevel | None:
    """Nærmeste klynge bak nåpris som overstiger strength-terskelen.

    BUY: klyngen skal være strengt under `current_price` (pullback-støtte).
    SELL: strengt over (pullback-motstand).
    """
    if direction == Direction.BUY:
        candidates = [c for c in clusters if c.price < current_price and c.strength >= min_strength]
        if not candidates:
            return None
        # Nærmest = minst avstand = størst pris (siden alle < current)
        return max(candidates, key=lambda c: c.price)

    # SELL
    candidates = [c for c in clusters if c.price > current_price and c.strength >= min_strength]
    if not candidates:
        return None
    return min(candidates, key=lambda c: c.price)


def _compute_sl(entry: float, direction: Direction, atr_buffer: float) -> float:
    """SL ligger `atr_buffer` forbi entry-nivået i retning motsatt trade."""
    if direction == Direction.BUY:
        return entry - atr_buffer
    return entry + atr_buffer


def _find_tp_cluster(
    clusters: list[ClusteredLevel],
    current_price: float,
    direction: Direction,
    entry: float,
    sl: float,
    horizon: Horizon,
    min_rr: float | None,
) -> tuple[ClusteredLevel, float] | None:
    """Finn TP-klynge per horisont-regler; returner (cluster, rr) eller None.

    Kandidat-rekkefølge (klynger i retning etter avstand):
    - SCALP: indeks 0 (nærmeste), fallback 1
    - SWING: indeks 1 (2. i retningen per PLAN § 5.2), fallback 2

    For hver kandidat: sjekk om R:R ≥ min_rr. Første som treffer vinner.
    `min_rr=None` skal ikke kalles her (MAKRO er håndtert før).
    """
    assert min_rr is not None, "MAKRO bør være håndtert før _find_tp_cluster"

    # Klynger i retning av trade, sortert etter avstand fra nåpris
    if direction == Direction.BUY:
        ahead = sorted(
            [c for c in clusters if c.price > current_price],
            key=lambda c: c.price,
        )
    else:
        ahead = sorted(
            [c for c in clusters if c.price < current_price],
            key=lambda c: -c.price,
        )

    if horizon == Horizon.SCALP:
        indices: tuple[int, ...] = (0, 1)
    else:  # SWING
        indices = (1, 2)

    for idx in indices:
        if idx >= len(ahead):
            continue
        candidate = ahead[idx]
        rr = _compute_rr(entry, sl, candidate.price, direction)
        if rr is None:
            continue
        if rr >= min_rr:
            return (candidate, rr)

    return None


def _compute_rr(
    entry: float,
    sl: float,
    tp: float,
    direction: Direction,
) -> float | None:
    """Reward/Risk-ratio. Returnerer `None` hvis risiko ≤ 0 (invalid setup)."""
    if direction == Direction.BUY:
        risk = entry - sl
        reward = tp - entry
    else:
        risk = sl - entry
        reward = entry - tp

    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


# Re-export for convenience
__all__ = [
    "Direction",
    "Horizon",
    "Setup",
    "SetupConfig",
    "ClusteredLevel",
    "compute_atr",
    "cluster_levels",
    "build_setup",
]


# Liten ekstra helper for type-annotering i framtidige caller-sites
HorizonLiteral = Literal["scalp", "swing", "makro"]
