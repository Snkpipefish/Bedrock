# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false
# pandas-stubs false-positives — se data/store.py for kontekst.

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

    Defaults matcher PLAN § 5.2-5.3 (k per horisont — ATR er D1 i
    produksjon, så buffer må skalere med forventet holdetid):
    - `cluster_atr_multiplier=0.3`: nivåer innenfor 0.3×ATR cluster sammen
    - `cluster_max_span_atr=0.5`: maks total bredde på en klynge (×ATR).
       Uten tak kunne transitiv kjeding sluke store soner (empirisk
       2026-06-12: 185 nivåer over 6.6×ATR for Gold) — entry/TP ble
       nær-vilkårlige punkter i en enorm sone
    - `sl_atr_multiplier=0.3`: SL-avstand for SCALP (×ATR forbi entry)
    - `sl_atr_multiplier_swing=1.0`: SL-avstand for SWING. En 7-21-dagers
       trade må overleve minst én normal dagsrange mot seg fra nivået;
       0.3×dATR ga scalp-stops på swing-horisont (live-data 2026-05/06:
       median holdetid 2.8t mot forventet 168-504t, SL-exits dominerte)
    - `sl_atr_multiplier_makro=1.5`: SL-avstand for MAKRO. Bredere buffer
       hindrer at trailing aktiveres på støy — makro-tese trenger plass til
       normal volatilitet uten å stenges på første mot-bevegelse
    - `min_entry_strength=0.6`: entry-klyngen må minst ha denne strength
    - `min_rr_scalp=1.5`, `min_rr_swing=2.5`: asymmetri-floor per horisont
    - `min_entry_distance_atr=0.0` / `max_entry_distance_atr=2.0`:
       avstandsbånd for entry-klyngen (×ATR bak nåpris). Uten max kunne
       entry ligge vilkårlig langt unna — limit-ordre som aldri fylles,
       eller fylles etter at tesen er død. Min er 0.0 (av) — pris som
       står PÅ et sterkt nivå er et gyldig entry-punkt
    - `tp_max_distance_atr_scalp=2.0` / `tp_max_distance_atr_swing=6.0`:
       horisont-vindu for TP-avstand (×ATR fra nåpris). Tommelfinger
       ~1 ATR/dag: SCALP ≤ 2 dager, SWING ≤ ~6 dager reise til target.
       Hindrer at TP glir ut i MAKRO-territorium
    """

    cluster_atr_multiplier: float = Field(default=0.3, gt=0.0)
    cluster_max_span_atr: float = Field(default=0.5, gt=0.0)
    sl_atr_multiplier: float = Field(default=0.3, gt=0.0)
    sl_atr_multiplier_swing: float = Field(default=1.0, gt=0.0)
    sl_atr_multiplier_makro: float = Field(default=1.5, gt=0.0)
    min_entry_strength: float = Field(default=0.6, ge=0.0, le=1.0)
    min_rr_scalp: float = Field(default=1.5, gt=0.0)
    min_rr_swing: float = Field(default=2.5, gt=0.0)
    min_entry_distance_atr: float = Field(default=0.0, ge=0.0)
    max_entry_distance_atr: float = Field(default=2.0, gt=0.0)
    tp_max_distance_atr_scalp: float = Field(default=2.0, gt=0.0)
    tp_max_distance_atr_swing: float = Field(default=6.0, gt=0.0)

    model_config = ConfigDict(extra="forbid")

    def tp_max_distance_atr_for(self, horizon: Horizon) -> float | None:
        """TP-vindu per horisont. MAKRO har ingen TP → None."""
        if horizon == Horizon.SCALP:
            return self.tp_max_distance_atr_scalp
        if horizon == Horizon.SWING:
            return self.tp_max_distance_atr_swing
        return None  # MAKRO

    def sl_atr_multiplier_for(self, horizon: Horizon) -> float:
        """SL-buffer skalerer med horisont — lengre hold = bredere buffer."""
        if horizon == Horizon.MAKRO:
            return self.sl_atr_multiplier_makro
        if horizon == Horizon.SWING:
            return self.sl_atr_multiplier_swing
        return self.sl_atr_multiplier

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
        raise ValueError(f"compute_atr: need >= period+1 bars ({period + 1}), got {len(ohlc)}")

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


def cluster_levels(
    levels: list[Level],
    buffer: float,
    max_span: float | None = None,
) -> list[ClusteredLevel]:
    """Merge nivåer innenfor `buffer` pris-avstand via transitiv single-link.

    Algoritme (greedy, sortert etter pris ASC):
    1. Sorter nivåer etter pris
    2. Gå gjennom; hvis nåværende nivå ligger innenfor `buffer` av
       **forrige** nivå i klyngen OG klyngens totale spenn holder seg
       innenfor `max_span`, legg til. Ellers start ny klynge
    3. For hver klynge: pris = strength-vektet sentroid, types =
       distinkte, strength = max_strength + 0.1 × (distinkte typer - 1),
       cap 1.0

    Transitiv kobling betyr at levels ved 100.0, 100.2, 100.5 med
    buffer=0.3 alle havner i samme klynge (kjede-effekt) fordi hver
    er innenfor `buffer` av den forrige. `max_span` begrenser kjede-
    effekten: uten tak kunne tette nivålister produsere klynger over
    flere ATR (empirisk 2026-06-12: 6.6×ATR for Gold) der "klynge-pris"
    mistet all presisjon.

    Params:
        levels: rå-liste fra detektor (typisk `detect_*`-output konkatenert)
        buffer: pris-avstand; typisk `atr × cluster_atr_multiplier` fra
            `SetupConfig` (default 0.3×ATR)
        max_span: maks avstand fra klyngens første til siste nivå.
            `None` = ubegrenset (bakoverkompatibelt for direkte callers)

    Returnerer tom liste for tom input. `buffer <= 0` → ingen merging
    (hver level blir sin egen klynge).
    """
    if not levels:
        return []

    sorted_by_price = sorted(levels, key=lambda lvl: lvl.price)

    clusters: list[list[Level]] = []
    current: list[Level] = [sorted_by_price[0]]

    for lvl in sorted_by_price[1:]:
        within_buffer = buffer > 0 and (lvl.price - current[-1].price) <= buffer
        within_span = max_span is None or (lvl.price - current[0].price) <= max_span
        if within_buffer and within_span:
            current.append(lvl)
        else:
            clusters.append(current)
            current = [lvl]
    clusters.append(current)

    return [_merge_cluster(group) for group in clusters]


def _merge_cluster(group: list[Level]) -> ClusteredLevel:
    """Bygg en `ClusteredLevel` fra en gruppe av nærliggende `Level`.

    - price = strength-vektet sentroid av medlemmene. Symmetrisk og
      deterministisk; med span-cap avviker sentroiden maks en halv
      klyngebredde fra ethvert medlem. (Tidligere "sterkestes pris" var
      tie-skjev: ved lik strength vant alltid lavest pris.)
    - strength = strongest.strength + 0.1 × (antall distinkte typer - 1),
      cap 1.0 → konfluens-bonus kun for ekte konfluens (swing + prior +
      round), ikke for N nabo-nivåer av samme type
    - types = distinkte i stabil rekkefølge
    """
    strongest = max(group, key=lambda lvl: lvl.strength)
    # Stabil rekkefølge: bevar første forekomst
    seen_types: list[LevelType] = []
    for lvl in group:
        if lvl.type not in seen_types:
            seen_types.append(lvl.type)
    confluence_bonus = 0.1 * (len(seen_types) - 1)
    strength = min(1.0, strongest.strength + confluence_bonus)

    weight_sum = sum(lvl.strength for lvl in group)
    if len(group) == 1:
        # Unngå FP-avvik fra (price×s)/s — bevar eksakt pris
        price = group[0].price
    elif weight_sum > 0:
        price = sum(lvl.price * lvl.strength for lvl in group) / weight_sum
    else:
        price = strongest.price

    return ClusteredLevel(
        price=float(price),
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
       og span-tak `config.cluster_max_span_atr × atr`
    2. Finn **entry-klynge**: nærmeste klynge *bak* nåpris som oppfyller
       `strength ≥ min_entry_strength` OG ligger innenfor avstandsbåndet
       `[min_entry_distance_atr, max_entry_distance_atr] × atr`. BUY =
       støtte under, SELL = motstand over. Ingen funnet → `None`
    3. **SL** = entry ± `config.sl_atr_multiplier × atr` (forbi entry-
       nivået i retning motsatt trade)
    4. **TP** per horisont (session 2026-06-12: indeks-regel erstattet
       av horisont-vindu — se `_find_tp_cluster`):
       - **SCALP/SWING**: nærmeste klynge i retningen som gir R:R ≥
         horisontens floor og ligger innenfor horisontens TP-vindu
         (`tp_max_distance_atr_*`)
       - **MAKRO**: ingen TP, returner `Setup` med `tp=None, rr=None`
    5. **Asymmetri-gate**: R:R må være ≥ `config.min_rr_for(horizon)`.
       Hvis ingen TP-kandidat tilfredsstiller → `None`

    `atr` tas som parameter (ikke beregnet her) slik at caller kan
    gjenbruke samme verdi på tvers av flere `build_setup`-kall for samme
    instrument (en per horisont, per retning).
    """
    cfg = config if config is not None else SetupConfig()

    buffer = cfg.cluster_atr_multiplier * atr
    clusters = cluster_levels(levels, buffer, max_span=cfg.cluster_max_span_atr * atr)
    if not clusters:
        return None

    entry_cluster = _find_entry_cluster(
        clusters,
        current_price,
        direction,
        cfg.min_entry_strength,
        min_distance=cfg.min_entry_distance_atr * atr,
        max_distance=cfg.max_entry_distance_atr * atr,
    )
    if entry_cluster is None:
        return None

    entry = entry_cluster.price
    sl = _compute_sl(entry, direction, cfg.sl_atr_multiplier_for(horizon) * atr)

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

    # SCALP/SWING: finn TP-klynge som oppfyller min R:R innenfor vinduet
    tp_max_atr = cfg.tp_max_distance_atr_for(horizon)
    assert tp_max_atr is not None  # MAKRO håndtert over
    tp_result = _find_tp_cluster(
        clusters=clusters,
        current_price=current_price,
        direction=direction,
        entry=entry,
        sl=sl,
        min_rr=cfg.min_rr_for(horizon),
        max_distance=tp_max_atr * atr,
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
    min_distance: float = 0.0,
    max_distance: float | None = None,
) -> ClusteredLevel | None:
    """Nærmeste klynge bak nåpris som overstiger strength-terskelen.

    BUY: klyngen skal være strengt under `current_price` (pullback-støtte).
    SELL: strengt over (pullback-motstand).

    `min_distance`/`max_distance` (absolutt pris-avstand, typisk k×ATR
    fra `SetupConfig`) avgrenser hvor entry-klyngen kan ligge: for langt
    unna = limit-ordre som aldri fylles eller fylles etter at tesen er
    død. `max_distance=None` = ubegrenset (bakoverkompatibelt).
    """

    def _in_band(c: ClusteredLevel) -> bool:
        dist = abs(current_price - c.price)
        if dist < min_distance:
            return False
        return max_distance is None or dist <= max_distance

    if direction == Direction.BUY:
        candidates = [
            c
            for c in clusters
            if c.price < current_price and c.strength >= min_strength and _in_band(c)
        ]
        if not candidates:
            return None
        # Nærmest = minst avstand = størst pris (siden alle < current)
        return max(candidates, key=lambda c: c.price)

    # SELL
    candidates = [
        c
        for c in clusters
        if c.price > current_price and c.strength >= min_strength and _in_band(c)
    ]
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
    min_rr: float | None,
    max_distance: float,
) -> tuple[ClusteredLevel, float] | None:
    """Nærmeste TP-klynge som oppfyller R:R-floor innenfor horisont-vinduet.

    Session 2026-06-12: indeks-regelen (SCALP=1. klynge, SWING=2. klynge)
    er erstattet av et horisont-vindu. Indeks-regelen var følsom for
    klynge-tetthet: med span-cap og W/M-nivåer ligger klynger typisk
    0.5-1×ATR fra hverandre, og "2. klynge" ga aldri R:R ≥ 2.5 med
    SWING-SL på 1×ATR — SWING sultet. Samtidig var indeks-semantikken
    inkonsistent med horisont-vinduene (2. klynge ≈ 1-3 dagers reise,
    ikke 7-21).

    Ny regel: gå gjennom klyngene i retningen, nærmest først, og velg
    den FØRSTE som både gir `rr ≥ min_rr` og ligger innenfor
    `max_distance` fra nåpris. Nærmest-først bevarer prinsippet om at
    vi ikke shopper etter høyest mulig R:R — vi tar det nærmeste reelle
    nivået som gjør traden verdt å ta. Vinduet hindrer at TP glir ut av
    horisonten (SWING-TP i MAKRO-distanse).

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

    for candidate in ahead:
        if abs(candidate.price - current_price) > max_distance:
            break  # sortert på avstand — alle videre er enda lenger unna
        rr = _compute_rr(entry, sl, candidate.price, direction)
        if rr is not None and rr >= min_rr:
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
    "ClusteredLevel",
    "Direction",
    "Horizon",
    "Setup",
    "SetupConfig",
    "build_setup",
    "cluster_levels",
    "compute_atr",
]


# Liten ekstra helper for type-annotering i framtidige caller-sites
HorizonLiteral = Literal["scalp", "swing", "makro"]
