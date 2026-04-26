# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false
# pandas-stubs false-positives — se data/store.py for kontekst.

"""`generate_signals` — full E2E-orchestrator: score + setup + hysterese.

Fase 5 session 24 (del 2): knytter `score_instrument` til setup-generator
og hysterese til én enkelt funksjon som returnerer komplett signal-
output for et instrument.

Flyt per (direction, horizon)-kombinasjon:

    InstrumentConfig → Engine.score → GroupResult
                                    ↓
    DataStore.get_prices_ohlc → compute_atr + detect_*_levels
                                    ↓
    build_setup(direction, horizon, current_price, atr, levels, config)
                                    ↓
    (prev snapshot?) → stabilize_setup → StableSetup
                                    ↓
                              SignalEntry
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bedrock.config.instruments import (
    InstrumentConfig,
    load_instrument_config,
)
from bedrock.engine.engine import AgriRules, Engine, FamilyResult, FinancialRules, GroupResult
from bedrock.orchestrator.score import (
    DEFAULT_INSTRUMENTS_DIR,
    OrchestratorError,
    _find_yaml,
)
from bedrock.setups.generator import (
    Direction,
    Horizon,
    Setup,
    SetupConfig,
    build_setup,
    compute_atr,
)
from bedrock.setups.hysteresis import (
    HysteresisConfig,
    SetupSnapshot,
    StableSetup,
    stabilize_setup,
)
from bedrock.setups.levels import (
    Level,
    detect_prior_period_levels,
    detect_round_numbers,
    detect_swing_levels,
    rank_levels,
)
from bedrock.setups.snapshot import load_snapshot, save_snapshot

# ---------------------------------------------------------------------------
# Result-modeller
# ---------------------------------------------------------------------------


class AnalogNeighbor(BaseModel):
    """Én historisk nabo fra K-NN-resultatet, persistert i SignalEntry.

    Per ADR-005 Fase 10 session 61: lagres på SignalEntry slik at UI
    kan vise mini-tabell uten å re-kjøre K-NN.
    """

    ref_date: str  # ISO-dato 'YYYY-MM-DD'
    similarity: float
    forward_return_pct: float
    max_drawdown_pct: float | None = None

    model_config = ConfigDict(extra="forbid")


class AnalogTrace(BaseModel):
    """Sammendrag av K-NN-resultatet for ett signal, samlet for UI-modal.

    `hit_rate_pct` er andelen naboer med `forward_return >= outcome_threshold_pct`,
    beregnet samme måte som `analog_hit_rate`-driveren — repetert her
    for narrative ("Y av N steg ≥X% innen Hd"). Tersklene som ble brukt
    er med så UI kan vise dem uten at orchestrator-konsumenter må slå
    opp YAML-config.

    Per ADR-005 B5 + § 6.5: K-NN-output er additivt — tomt felt
    (None på SignalEntry) betyr "ingen analog-config eller ingen data
    tilgjengelig", ikke "K-NN var bevisst tomt".
    """

    asset_class: str
    horizon_days: int
    outcome_threshold_pct: float
    n_neighbors: int  # antall faktiske naboer (k er bestilt antall)
    hit_rate_pct: float  # 0..100
    avg_return_pct: float
    avg_drawdown_pct: float | None = None
    dims_used: list[str] = Field(default_factory=list)  # navn på dim som var tilgjengelig
    neighbors: list[AnalogNeighbor] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SignalEntry(BaseModel):
    """Ett kandidat-signal for en (direction, horizon)-kombinasjon.

    `families` og `active_families` er explain-trace-felt fra Engine,
    persistert ut i signals.json så UI kan vise driver-by-driver
    forklaring i modal (Fase 9 runde 2 session 52). Defaultet til tom
    dict / 0 så eldre fixtures og direkte instansieringer i tester ikke
    brekker — `_build_entry` populerer dem alltid fra GroupResult.

    `analog` (Fase 10 session 61) er K-NN-trace fra `find_analog_cases`
    samlet til UI-narrative. None hvis instrumentet ikke har en
    `analog`-familie i YAML eller hvis K-NN feilet (skip_missing).
    """

    instrument: str
    direction: Direction
    horizon: Horizon
    score: float
    grade: str
    max_score: float
    min_score_publish: float
    published: bool  # score ≥ min_score_publish
    setup: StableSetup | None = None  # None hvis build_setup returnerte None
    skip_reason: str | None = None  # hvorfor setup er None
    gates_triggered: list[str] = Field(default_factory=list)
    families: dict[str, FamilyResult] = Field(default_factory=dict)
    active_families: int = 0
    analog: AnalogTrace | None = None

    model_config = ConfigDict(extra="forbid")


class OrchestratorResult(BaseModel):
    """Full resultat-pakke for én `generate_signals`-kjøring."""

    instrument: str
    run_ts: datetime
    entries: list[SignalEntry] = Field(default_factory=list)
    snapshot_written: Path | None = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# Default horisont-sett for agri (som ikke har horisont i Engine-scoring).
_DEFAULT_AGRI_HORIZONS: tuple[Horizon, ...] = (
    Horizon.SCALP,
    Horizon.SWING,
    Horizon.MAKRO,
)

# YAML bruker uppercase horisont-strenger (PLAN § 4.2 / 4.3); `Horizon`-
# enum bruker lowercase `.value`. Disse holder mapping-en på ett sted.
_YAML_TO_ENUM: dict[str, Horizon] = {
    "SCALP": Horizon.SCALP,
    "SWING": Horizon.SWING,
    "MAKRO": Horizon.MAKRO,
}
_ENUM_TO_YAML: dict[Horizon, str] = {v: k for k, v in _YAML_TO_ENUM.items()}


def _yaml_key_from_horizon(h: Horizon) -> str:
    """Enum → YAML-nøkkel (uppercase)."""
    return _ENUM_TO_YAML[h]


def _horizon_from_name(name: str) -> Horizon:
    """Bruker-input (uppercase/lowercase) → Horizon-enum."""
    upper = name.upper()
    if upper not in _YAML_TO_ENUM:
        raise OrchestratorError(f"Unknown horizon {name!r}. Valid: {sorted(_YAML_TO_ENUM.keys())}")
    return _YAML_TO_ENUM[upper]


def generate_signals(
    instrument_id: str,
    store: Any,
    *,
    horizons: list[str] | None = None,
    directions: list[Direction] | None = None,
    instruments_dir: Path | str | None = None,
    defaults_dir: Path | str | None = None,
    snapshot_path: Path | str | None = None,
    now: datetime | None = None,
    price_tf: str = "D1",
    price_lookback: int = 250,
    swing_window: int = 5,
    round_number_step: float | None = None,
    setup_config: SetupConfig | None = None,
    hysteresis_config: HysteresisConfig | None = None,
    engine: Engine | None = None,
    write_snapshot: bool = True,
) -> OrchestratorResult:
    """Full signal-generering: score + setup + hysterese.

    - `horizons`: undersett av horisontene å generere. Financial: default
      alle fra YAML. Agri: default (SCALP, SWING, MAKRO) — brukes kun
      til setup-siden (scoring gjøres én gang uten horisont for agri).
    - `directions`: default `[BUY, SELL]`.
    - `snapshot_path`: brukes til både opplasting av forrige tilstand
      og til skriving av ny. `None` = ingen hysterese, ingen skriving.
    - `now`: default `datetime.now(timezone.utc)`. Settbart for
      determinisme i tester.
    - `round_number_step`: hvis satt, legges round-number-nivåer til
      level-listen. Default None (ikke inkluder).

    Returnerer `OrchestratorResult` med én `SignalEntry` per (direction,
    horizon)-kombinasjon, uavhengig av om setup faktisk ble bygget.
    Failed setups har `setup=None` og `skip_reason` satt.
    """
    resolved_inst_dir = (
        Path(instruments_dir) if instruments_dir is not None else DEFAULT_INSTRUMENTS_DIR
    )
    cfg = load_instrument_config(
        _find_yaml(instrument_id, resolved_inst_dir),
        defaults_dir=defaults_dir,
    )

    run_ts = now or datetime.now(timezone.utc)
    directions_list = directions if directions is not None else [Direction.BUY, Direction.SELL]
    horizons_list = _resolve_horizons(cfg, horizons)

    # Market-data én gang
    ohlc = store.get_prices_ohlc(cfg.instrument.id, price_tf, price_lookback)
    if len(ohlc) < 2:
        raise OrchestratorError(
            f"Ikke nok prisdata for {cfg.instrument.id} ({len(ohlc)} barer, behov ≥ 2)."
        )
    current_price = float(ohlc["close"].iloc[-1])
    atr = compute_atr(ohlc)
    levels = _build_level_list(ohlc, current_price, swing_window, round_number_step)

    # Snapshot for hysterese
    previous_snapshot = _load_previous_snapshot(snapshot_path)

    # Pre-compute score per (horisont, retning). Per ADR-006 (session 95b)
    # er score nå direction-bevisst — flippes på familier med
    # polarity="directional" når direction=SELL.
    scores_by_horizon_dir = _compute_scores(cfg, store, horizons_list, directions_list, engine)

    # Generer entries
    entries: list[SignalEntry] = []
    new_stable_setups: list[StableSetup] = []
    for horizon in horizons_list:
        for direction in directions_list:
            group_result = scores_by_horizon_dir[(horizon, direction)]
            entry = _build_entry(
                cfg=cfg,
                direction=direction,
                horizon=horizon,
                group_result=group_result,
                current_price=current_price,
                atr=atr,
                levels=levels,
                previous_snapshot=previous_snapshot,
                run_ts=run_ts,
                setup_config=setup_config,
                hysteresis_config=hysteresis_config,
                store=store,
            )
            entries.append(entry)
            if entry.setup is not None:
                new_stable_setups.append(entry.setup)

    # Skriv ny snapshot hvis angitt
    snapshot_written: Path | None = None
    if snapshot_path is not None and write_snapshot:
        new_snapshot = SetupSnapshot(run_ts=run_ts, setups=new_stable_setups)
        snapshot_written = save_snapshot(new_snapshot, Path(snapshot_path))

    return OrchestratorResult(
        instrument=cfg.instrument.id,
        run_ts=run_ts,
        entries=entries,
        snapshot_written=snapshot_written,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_horizons(cfg: InstrumentConfig, requested: list[str] | None) -> list[Horizon]:
    """Bestem hvilke horisonter som skal genereres for.

    YAML-nøkler er uppercase ("SCALP" etc.); enum-verdier er lowercase.
    Caller kan bruke hvilken casing som helst.
    """
    if isinstance(cfg.rules, FinancialRules):
        available_upper = set(cfg.rules.horizons.keys())
        if requested is None:
            return [_YAML_TO_ENUM[h] for h in sorted(available_upper)]
        unknown = [h for h in requested if h.upper() not in available_upper]
        if unknown:
            raise OrchestratorError(
                f"Horizons {unknown} not defined for {cfg.instrument.id!r}. "
                f"Available: {sorted(available_upper)}"
            )
        return [_horizon_from_name(h) for h in requested]

    if isinstance(cfg.rules, AgriRules):
        if requested is None:
            return list(_DEFAULT_AGRI_HORIZONS)
        return [_horizon_from_name(h) for h in requested]

    raise OrchestratorError(f"Unknown rules type: {type(cfg.rules).__name__}")


def _build_level_list(
    ohlc: Any,
    current_price: float,
    swing_window: int,
    round_number_step: float | None,
) -> list[Level]:
    """Bygg samlet, rangert nivå-liste for setup-generering.

    Inkluderer swing + prior-daily. Round numbers legges kun til hvis
    `round_number_step` er angitt (avhengig av asset-klasse).
    """
    levels: list[Level] = []
    levels.extend(detect_swing_levels(ohlc, window=swing_window))
    if len(ohlc) >= 2:
        levels.extend(detect_prior_period_levels(ohlc, period="D"))
    if round_number_step is not None:
        levels.extend(
            detect_round_numbers(
                current_price=current_price,
                step=round_number_step,
                count_above=3,
                count_below=3,
            )
        )
    return rank_levels(levels)


def _load_previous_snapshot(
    snapshot_path: Path | str | None,
) -> SetupSnapshot | None:
    if snapshot_path is None:
        return None
    return load_snapshot(Path(snapshot_path))


def _compute_scores(
    cfg: InstrumentConfig,
    store: Any,
    horizons: list[Horizon],
    directions: list[Direction],
    engine: Engine | None,
) -> dict[tuple[Horizon, Direction], GroupResult]:
    """Score per (horisont, retning).

    Per ADR-006 (session 95b) er Engine.score direction-bevisst.
    - Financial: én Engine.score-call per (horisont, retning).
    - Agri: én score per retning (agri har ingen horisont-splitt på
      scoring-siden), delt på alle horisonter.
    """
    eng = engine or Engine()
    out: dict[tuple[Horizon, Direction], GroupResult] = {}

    if isinstance(cfg.rules, AgriRules):
        for direction in directions:
            single = eng.score(
                cfg.instrument.id, store, cfg.rules, horizon=None, direction=direction
            )
            for h in horizons:
                out[(h, direction)] = single
        return out

    assert isinstance(cfg.rules, FinancialRules)  # nosec B101
    for h in horizons:
        for direction in directions:
            out[(h, direction)] = eng.score(
                cfg.instrument.id,
                store,
                cfg.rules,
                horizon=_yaml_key_from_horizon(h),
                direction=direction,
            )
    return out


def _get_min_score_publish(cfg: InstrumentConfig, horizon: Horizon) -> float:
    """Publish-gulv per horisont.

    - Financial: fra `HorizonSpec.min_score_publish` (YAML-nøkkel er
      uppercase, mapper fra enum)
    - Agri: fra `AgriRules.min_score_publish` (felles for alle horisonter)
    """
    if isinstance(cfg.rules, FinancialRules):
        return cfg.rules.horizons[_yaml_key_from_horizon(horizon)].min_score_publish
    assert isinstance(cfg.rules, AgriRules)  # nosec B101
    return cfg.rules.min_score_publish


def _build_analog_trace(
    cfg: InstrumentConfig,
    store: Any,
) -> AnalogTrace | None:
    """Bygg AnalogTrace fra K-NN hvis instrumentet har en `analog`-familie.

    Plukker driver-params fra første `analog`-driver i YAML for å bestemme
    asset_class, k, horizon_days, outcome_threshold_pct, min_history_days,
    dim_weights. Hvis K-NN returnerer empty (mangler outcomes / mangler
    extractor), returnerer None — caller (modal-UI) viser "ingen analog
    tilgjengelig".

    Per ADR-005 + § 6.5: defensive — alle exceptions fanges, returnerer
    None. Trace er sekundær til scoring.
    """
    families = getattr(cfg.rules, "families", None) or {}
    analog_family = families.get("analog")
    if analog_family is None:
        return None

    # Plukk parametre fra første driver i analog-familien
    drivers = list(getattr(analog_family, "drivers", None) or [])
    if not drivers:
        return None
    first = drivers[0]
    params = dict(getattr(first, "params", None) or {})

    asset_class = params.get("asset_class")
    if not asset_class:
        return None

    k = int(params.get("k", 5))
    horizon_days = int(params.get("horizon_days", 30))
    outcome_threshold_pct = float(params.get("outcome_threshold_pct", 3.0))
    min_history_days = int(params.get("min_history_days", 365))
    dim_weights = params.get("dim_weights")

    # Lat import for å unngå sirkulær (data.analog → engine → orchestrator)
    from bedrock.data.analog import (
        ASSET_CLASS_DIMS,
        extract_query_from_latest,
        find_analog_cases,
    )

    if asset_class not in ASSET_CLASS_DIMS:
        return None

    try:
        query = extract_query_from_latest(store, cfg.instrument, asset_class, skip_missing=True)
    except Exception:
        return None

    if not query:
        return None

    try:
        result = find_analog_cases(
            store,
            cfg.instrument.id,
            cfg.instrument,
            asset_class,
            query,
            k=k,
            dim_weights=dim_weights,
            horizon_days=horizon_days,
            min_history_days=min_history_days,
        )
    except Exception:
        return None

    if result.empty:
        return None

    n = len(result)
    hits = int((result["forward_return_pct"] >= outcome_threshold_pct).sum())
    hit_rate_pct = (hits / n) * 100.0
    avg_return_pct = float(result["forward_return_pct"].mean())

    drawdowns = result["max_drawdown_pct"].dropna()
    avg_drawdown_pct = float(drawdowns.mean()) if not drawdowns.empty else None

    neighbors = [
        AnalogNeighbor(
            ref_date=row.ref_date.strftime("%Y-%m-%d"),
            similarity=float(row.similarity),
            forward_return_pct=float(row.forward_return_pct),
            max_drawdown_pct=(
                None if pd_is_na(row.max_drawdown_pct) else float(row.max_drawdown_pct)
            ),
        )
        for row in result.itertuples(index=False)
    ]

    return AnalogTrace(
        asset_class=asset_class,
        horizon_days=horizon_days,
        outcome_threshold_pct=outcome_threshold_pct,
        n_neighbors=n,
        hit_rate_pct=hit_rate_pct,
        avg_return_pct=avg_return_pct,
        avg_drawdown_pct=avg_drawdown_pct,
        dims_used=sorted(query),
        neighbors=neighbors,
    )


def pd_is_na(v: Any) -> bool:
    """Test om en verdi er pandas NaN (uten å kreve pandas-import på toppen)."""
    import pandas as pd

    return bool(pd.isna(v))


def _build_entry(
    *,
    cfg: InstrumentConfig,
    direction: Direction,
    horizon: Horizon,
    group_result: GroupResult,
    current_price: float,
    atr: float,
    levels: list[Level],
    previous_snapshot: SetupSnapshot | None,
    run_ts: datetime,
    setup_config: SetupConfig | None,
    hysteresis_config: HysteresisConfig | None,
    store: Any | None = None,
) -> SignalEntry:
    """Bygg én SignalEntry — score + (kanskje) stabilisert setup.

    `store` brukes til å hente analog-trace (K-NN) hvis instrumentet
    har en `analog`-familie i YAML. None → analog-trace skippes (matcher
    eldre call-sites + tester som ikke trenger K-NN).
    """
    min_publish = _get_min_score_publish(cfg, horizon)
    published = group_result.score >= min_publish

    analog_trace = _build_analog_trace(cfg, store) if store is not None else None

    # Bygg rå setup
    raw_setup: Setup | None = build_setup(
        instrument=cfg.instrument.id,
        direction=direction,
        horizon=horizon,
        current_price=current_price,
        atr=atr,
        levels=levels,
        config=setup_config,
    )

    if raw_setup is None:
        return SignalEntry(
            instrument=cfg.instrument.id,
            direction=direction,
            horizon=horizon,
            score=group_result.score,
            grade=group_result.grade,
            max_score=group_result.max_score,
            min_score_publish=min_publish,
            published=False,  # ingen setup → ingen publish uansett
            setup=None,
            skip_reason="build_setup returned None (no asymmetric setup found)",
            gates_triggered=list(group_result.gates_triggered),
            families=dict(group_result.families),
            active_families=group_result.active_families,
            analog=analog_trace,
        )

    # Stabiliser hvis previous finnes
    previous: StableSetup | None = None
    if previous_snapshot is not None:
        previous = previous_snapshot.find(cfg.instrument.id, direction, horizon)

    stable = stabilize_setup(
        new_setup=raw_setup,
        previous=previous,
        now=run_ts,
        config=hysteresis_config,
    )

    return SignalEntry(
        instrument=cfg.instrument.id,
        direction=direction,
        horizon=horizon,
        score=group_result.score,
        grade=group_result.grade,
        max_score=group_result.max_score,
        min_score_publish=min_publish,
        published=published,
        setup=stable,
        skip_reason=None,
        gates_triggered=list(group_result.gates_triggered),
        families=dict(group_result.families),
        active_families=group_result.active_families,
        analog=analog_trace,
    )


__all__ = [
    "AnalogNeighbor",
    "AnalogTrace",
    "OrchestratorResult",
    "SignalEntry",
    "generate_signals",
]
