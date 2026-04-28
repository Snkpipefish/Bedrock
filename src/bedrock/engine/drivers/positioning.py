"""Positioning-familie drivere (Sub-fase 12.5 session 70 + 12.7 R3).

Erstatter ``sma200_align``-placeholder i positioning-familien. Bruker
COT-data fra ``DataStore.get_cot()`` til å beregne hvor ekstrem
managed-money-positioneringen er relativt til historikken.

To drivere implementert:

- ``positioning_mm_pct``: rank-percentile (0-100) av MM net positioning
  over rolling window. Mappes til 0..1. **R3 (sub-fase 12.7)**: utvidet
  med horisont-bevisste modes via ``params["mode"]`` per ADR-010 og
  ``docs/driver_horizon_pattern.md`` § 1.1. Default-output (mode=None)
  er bit-identisk med pre-R3 — kontraktuelt krav per § 5.3.
- ``cot_z_score``: robust z-score (median+MAD) av MM net positioning,
  mappet til 0..1 via terskel-trapp matching ``momentum_z``-konvensjonen.
  Ikke endret i R3.

Begge er **monotont bull**: høy MM long-posisjon → høy score (1.0).
Lav/negativ MM net → lav score (0.0). Direction-spesifikk inversjon
(f.eks. for SELL-direksjon å score høyt når MM er ekstrem long som
contrarian-signal) hører hjemme i regel-design, ikke i driveren.

Begge drivere er defensive per driver-kontrakt: feil i config-lookup,
data-oppslag, eller utilstrekkelig historikk → 0.0 + log, ingen exception.

Params (felles):
- ``report``: ``"disaggregated"`` (default) eller ``"legacy"``. Bestemmer
  hvilken COT-tabell som leses.
- ``lookback_weeks``: rolling-vindu (default 52). MIN_OBS_FOR_PCTILE
  håndheves uansett (~26 uker). Større vindu = mer stabil percentile.
  Når ``mode`` er satt på ``positioning_mm_pct`` overstyres
  ``lookback_weeks`` av mode-spesifikt vindu (52 for pct_12m/delta_*_z,
  156 for pct_36m).
- ``metric``: ``"mm_net"`` (default), eller ``"mm_net_pct"`` for å
  normalisere mot open_interest. ``mm_net_pct`` reduserer scale-bias
  når OI vokser/krymper kraftig (anbefalt for instrumenter med stor
  OI-variasjon).

positioning_mm_pct-spesifikk (R3):
- ``mode``: feature-velger. ``None``/utelatt (default) = dagens output
  (bit-identisk pre-R3). ``"pct_12m"`` = rank-percentile over 52-uke-
  vindu (≡ default for samme lookback). ``"pct_36m"`` = rank-percentile
  over 156-uke-vindu, fall-back til pct_12m ved utilstrekkelig
  historikk + log. ``"delta_5d_z"`` = z-score av 1-rapport-delta
  (~7d natural for ukentlig COT) over 52-rapport-vindu, mappet til
  [0..1] via momentum-trapp. ``"delta_20d_z"`` = 4-rapport-delta
  (~28d natural) over 52-rapport-vindu. ``"extreme_flag_hard"`` =
  1.0 ved pct_12m ≥ 0.98 eller ≤ 0.02, ellers 0.0.
  ``"extreme_flag_soft"`` = 1.0 ved pct_12m ≥ 0.95 eller ≤ 0.05,
  ellers 0.0. Ukjent mode → log warning + fall-back til default.
- ``_horizon``: engine-injisert kontekst-key per ADR-010. Lest av
  driver men brukt ikke til å endre output i R3 (per § 5.3 R3-
  kontrakt).

cot_z_score-spesifikk:
- ``z_thresholds``: optional override av step-mapping. Default matcher
  ``momentum_z``-konvensjon: z≥2→1.0, z≥1→0.75, z≥0.5→0.6, z≥0→0.5,
  z≥−0.5→0.3, ellers 0.0.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import register
from bedrock.engine.drivers._stats import (
    MIN_OBS_FOR_PCTILE,
    rank_percentile,
    rolling_z,
)

_log = structlog.get_logger(__name__)

_DEFAULT_LOOKBACK = 52
_DEFAULT_REPORT = "disaggregated"
_DEFAULT_METRIC = "mm_net"

# R3 (sub-fase 12.7): mode-spesifikke historikk-vinduer.
# Begrunnelse: 12m ≈ 52 ukentlig-obs (matcher dagens default),
# 36m ≈ 156 ukentlig-obs (matcher § 1.1 i driver_horizon_pattern).
_LOOKBACK_PCT_12M = 52
_LOOKBACK_PCT_36M = 156
# delta_5d_z og delta_20d_z på ukentlig COT tolkes som 1-rapport- og
# 4-rapport-delta (≈7d og ≈28d natural). 52 historikk-obs av delta-
# serien matcher pct_12m-vinduet for konsistens.
_DELTA_5D_REPORTS = 1
_DELTA_20D_REPORTS = 4
_LOOKBACK_DELTA = 52  # antall historikk-obs av diff-serien for rolling-z

# Tersklene for extreme_flag-modes (PLAN § 19.3 låst).
_EXTREME_HARD_HI = 0.98
_EXTREME_HARD_LO = 0.02
_EXTREME_SOFT_HI = 0.95
_EXTREME_SOFT_LO = 0.05


# Default mapping for cot_z_score: matcher momentum_z-trappen i trend.py
# slik at familier som blander z-baserte drivere får konsistent skalering.
_DEFAULT_Z_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (2.0, 1.0),
    (1.0, 0.75),
    (0.5, 0.6),
    (0.0, 0.5),
    (-0.5, 0.3),
)


def _z_to_score_positive(z: float) -> float:
    """Map z-score til [0..1] via momentum-trapp (positiv-bull-konvensjon).

    Brukt av positioning delta_*_z-modes der positiv z = økt MM long =
    bull-of-instrument. Speilet av _DEFAULT_Z_THRESHOLDS men inline
    for å holde mode-koden lesbar.
    """
    if z >= 2.0:
        return 1.0
    if z >= 1.0:
        return 0.75
    if z >= 0.5:
        return 0.6
    if z >= 0.0:
        return 0.5
    if z >= -0.5:
        return 0.3
    return 0.0


def _extreme_flag(pct_0_to_1: float, *, hard: bool) -> float:
    """Returner 1.0 hvis pct er ekstrem, ellers 0.0.

    hard=True: 0.98/0.02-tersklene (extreme_flag_hard, PLAN § 19.3).
    hard=False: 0.95/0.05-tersklene (extreme_flag_soft).
    """
    hi = _EXTREME_HARD_HI if hard else _EXTREME_SOFT_HI
    lo = _EXTREME_HARD_LO if hard else _EXTREME_SOFT_LO
    if pct_0_to_1 >= hi or pct_0_to_1 <= lo:
        return 1.0
    return 0.0


# ---------------------------------------------------------------------------
# Felles helper
# ---------------------------------------------------------------------------


def _resolve_contract(instrument: str) -> tuple[str, str] | None:
    """Slå opp ``cot_contract`` + ``cot_report`` fra instrument-config.

    Returnerer ``(contract, report)`` eller ``None`` hvis lookup feiler
    eller instrument mangler ``cot_contract``. Lazy-import av
    ``find_instrument`` for å unngå sirkulær import (samme mønster som
    ``analog.py``).
    """
    from bedrock.cli._instrument_lookup import find_instrument

    try:
        cfg = find_instrument(instrument, "config/instruments")
    except Exception as exc:
        _log.warning(
            "positioning.instrument_lookup_failed",
            instrument=instrument,
            error=str(exc),
        )
        return None

    meta = cfg.instrument
    if not meta.cot_contract:
        _log.debug(
            "positioning.no_cot_contract",
            instrument=instrument,
        )
        return None

    report = meta.cot_report or _DEFAULT_REPORT
    return meta.cot_contract, report


def _compute_metric(df: pd.DataFrame, metric: str) -> pd.Series | None:
    """Beregn metrikk-serie fra COT-DataFrame.

    Returnerer pd.Series (ts-aligned med report_date) eller ``None`` ved
    ukjent metric. Faller graceful til ``None`` ved manglende kolonner.
    """
    if metric == "mm_net":
        if "mm_long" not in df.columns or "mm_short" not in df.columns:
            return None
        return df["mm_long"].astype("float64") - df["mm_short"].astype("float64")

    if metric == "mm_net_pct":
        if "mm_long" not in df.columns or "mm_short" not in df.columns:
            return None
        if "open_interest" not in df.columns:
            return None
        net = df["mm_long"].astype("float64") - df["mm_short"].astype("float64")
        oi = df["open_interest"].astype("float64").replace(0, pd.NA)
        return net / oi  # NA-propagering tar seg av OI=0-tilfeller

    # Legacy COT (uten disaggregated MM-splitt): bruk non-commercial som
    # nærmeste MM-ekvivalent. For indekser og andre kontrakter uten
    # disaggregated-rapport er dette den eneste tilgjengelige spec-metrikken.
    if metric == "noncomm_net":
        if "noncomm_long" not in df.columns or "noncomm_short" not in df.columns:
            return None
        return df["noncomm_long"].astype("float64") - df["noncomm_short"].astype("float64")

    if metric == "noncomm_net_pct":
        if "noncomm_long" not in df.columns or "noncomm_short" not in df.columns:
            return None
        if "open_interest" not in df.columns:
            return None
        net = df["noncomm_long"].astype("float64") - df["noncomm_short"].astype("float64")
        oi = df["open_interest"].astype("float64").replace(0, pd.NA)
        return net / oi

    return None


def _load_metric_series(
    store: Any,
    instrument: str,
    params: dict,
) -> tuple[float, list[float]] | None:
    """Felles datastrøm-loader for begge drivere.

    Returnerer ``(current, history)`` der ``current`` er siste verdi og
    ``history`` er alle tidligere observasjoner i lookback-vindu (siste
    først ekskludert). Returnerer ``None`` ved feil — caller logger.
    """
    contract_info = _resolve_contract(instrument)
    if contract_info is None:
        return None
    contract, report = contract_info

    lookback = int(params.get("lookback_weeks", _DEFAULT_LOOKBACK))
    metric = str(params.get("metric", _DEFAULT_METRIC))

    try:
        df = store.get_cot(contract, report=report, last_n=lookback + 1)
    except KeyError:
        _log.debug(
            "positioning.cot_data_missing",
            instrument=instrument,
            contract=contract,
            report=report,
        )
        return None
    except Exception as exc:
        _log.warning(
            "positioning.cot_fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return None

    series = _compute_metric(df, metric)
    if series is None:
        _log.warning(
            "positioning.unknown_metric",
            instrument=instrument,
            metric=metric,
        )
        return None

    series = series.dropna()
    if len(series) < MIN_OBS_FOR_PCTILE + 1:
        # Trenger minimum 27 obs: 1 current + 26 history
        _log.debug(
            "positioning.short_history",
            instrument=instrument,
            n=len(series),
            required=MIN_OBS_FOR_PCTILE + 1,
        )
        return None

    current = float(series.iloc[-1])
    history = [float(v) for v in series.iloc[:-1]]
    return current, history


# ---------------------------------------------------------------------------
# positioning_mm_pct
# ---------------------------------------------------------------------------


def _load_metric_full_series(
    store: Any,
    instrument: str,
    params: dict,
    *,
    n_obs: int,
) -> pd.Series | None:
    """Hent metric-serie med eksplisitt antall obs (inkl. current).

    Felles loader for R3-modes som trenger full serie (delta-modes må
    bygge diff-serien) eller utvidet historikk (pct_36m). Returnerer
    pd.Series sortert chronologisk eller None ved feil.

    Skiller seg fra ``_load_metric_series`` ved å returnere hele
    serien som pd.Series, ikke ``(current, history)``-tuple. Behold den
    eldre helperen urørt for å garantere bit-identisk output for
    ``cot_z_score`` og ICE/Euronext-variantene som ikke er R3-scope.
    """
    contract_info = _resolve_contract(instrument)
    if contract_info is None:
        return None
    contract, report = contract_info

    metric = str(params.get("metric", _DEFAULT_METRIC))

    try:
        df = store.get_cot(contract, report=report, last_n=n_obs)
    except KeyError:
        _log.debug(
            "positioning.cot_data_missing",
            instrument=instrument,
            contract=contract,
            report=report,
        )
        return None
    except Exception as exc:
        _log.warning(
            "positioning.cot_fetch_failed",
            instrument=instrument,
            error=str(exc),
        )
        return None

    series = _compute_metric(df, metric)
    if series is None:
        _log.warning(
            "positioning.unknown_metric",
            instrument=instrument,
            metric=metric,
        )
        return None

    series = series.dropna()
    if series.empty:
        return None
    return series


def _mode_pct(series: pd.Series, instrument: str, lookback: int) -> float | None:
    """Beregn rank-percentile / 100 over de siste `lookback` obs.

    Returnerer None ved utilstrekkelig historikk slik at caller kan
    fall-back eller returnere 0.0.
    """
    if len(series) < MIN_OBS_FOR_PCTILE + 1:
        _log.debug(
            "positioning.short_history_for_pct",
            instrument=instrument,
            n=len(series),
            required=MIN_OBS_FOR_PCTILE + 1,
        )
        return None
    window = series.iloc[-(lookback + 1) :] if len(series) > lookback else series
    if len(window) < MIN_OBS_FOR_PCTILE + 1:
        return None
    current = float(window.iloc[-1])
    history = [float(v) for v in window.iloc[:-1]]
    pct = rank_percentile(current, history)
    if pct is None:
        return None
    return pct / 100.0


def _mode_delta_z(
    series: pd.Series,
    instrument: str,
    *,
    delta_reports: int,
    lookback: int,
) -> float | None:
    """Beregn z-score av N-rapport-delta over `lookback` historikk-obs.

    For ukentlig COT tolkes ``delta_reports=1`` som "delta_5d_z" (≈7d
    natural) og ``delta_reports=4`` som "delta_20d_z" (≈28d natural).
    Frekvens-translasjonen logges i debug per call slik at den ikke er
    skjult i kildekoden — viktig når delta_*_z-output sammenlignes på
    tvers av drivere med ulike datafrekvenser (real_yield er daglig).
    """
    # Trenger delta_reports + lookback + 1 obs for å bygge diff-serien
    # med 1 current-diff og `lookback` historikk-diffs.
    required = delta_reports + lookback + 1
    if len(series) < required:
        _log.debug(
            "positioning.short_history_for_delta",
            instrument=instrument,
            delta_reports=delta_reports,
            n=len(series),
            required=required,
        )
        return None

    diff_series = series.diff(periods=delta_reports).dropna()
    if len(diff_series) < MIN_OBS_FOR_PCTILE + 1:
        return None

    _log.debug(
        "positioning.delta_z_natural_translation",
        instrument=instrument,
        delta_reports=delta_reports,
        natural_days=delta_reports * 7,
        note="weekly COT data; delta interpreted as N-report-delta",
    )

    current_diff = float(diff_series.iloc[-1])
    history_diff = [float(v) for v in diff_series.iloc[-(lookback + 1) : -1]]
    z = rolling_z(current_diff, history_diff)
    if z is None:
        return None
    return _z_to_score_positive(z)


@register("positioning_mm_pct")
def positioning_mm_pct(store: Any, instrument: str, params: dict) -> float:
    """Rank-percentile av MM net positioning, normalisert til 0..1.

    Default (mode=None) returnerer:
    - 1.0 ved ekstrem MM long (top-percentile)
    - 0.5 ved median posisjonering
    - 0.0 ved ekstrem MM short (bunn-percentile)

    R3 (sub-fase 12.7): horisont-bevisst via ``params["mode"]``. Se
    docstring øverst i modulen for full mode-tabell. Default-output
    (mode=None) er bit-identisk med pre-R3.

    Defensiv 0.0-retur ved manglende COT-data, ukjent contract eller
    utilstrekkelig historikk.
    """
    # ADR-010: les _horizon for fremtidig bruk. R3-kontrakt: ikke endre
    # default-output basert på _horizon. Verdi logges via debug ved
    # eksplisitt mode-valg under.
    horizon = params.get("_horizon")  # noqa: F841 — bevisst lest for ADR-010
    mode = params.get("mode")

    if mode is None:
        # Bit-identisk pre-R3: dagens flow uendret.
        loaded = _load_metric_series(store, instrument, params)
        if loaded is None:
            return 0.0
        current, history = loaded
        pct = rank_percentile(current, history)
        if pct is None:
            return 0.0
        return round(pct / 100.0, 4)

    # Eksplisitt mode-håndtering (R3-utvidelse).
    if mode == "pct_12m":
        series = _load_metric_full_series(store, instrument, params, n_obs=_LOOKBACK_PCT_12M + 1)
        if series is None:
            return 0.0
        result = _mode_pct(series, instrument, _LOOKBACK_PCT_12M)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        series = _load_metric_full_series(store, instrument, params, n_obs=_LOOKBACK_PCT_36M + 1)
        if series is None:
            return 0.0
        # Forsøk pct_36m først; fall-back til pct_12m hvis utilstrekkelig
        # 36m-historikk. Per § 1.1 i driver_horizon_pattern.md: ikke 0.0,
        # det ville maskere at instrumentet er yngre enn vinduet.
        result = _mode_pct(series, instrument, _LOOKBACK_PCT_36M)
        if result is None:
            _log.info(
                "positioning.pct_36m_fallback_to_12m",
                instrument=instrument,
                available_obs=len(series),
                required=_LOOKBACK_PCT_36M + 1,
            )
            result = _mode_pct(series, instrument, _LOOKBACK_PCT_12M)
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        series = _load_metric_full_series(
            store,
            instrument,
            params,
            n_obs=_DELTA_5D_REPORTS + _LOOKBACK_DELTA + 1,
        )
        if series is None:
            return 0.0
        result = _mode_delta_z(
            series,
            instrument,
            delta_reports=_DELTA_5D_REPORTS,
            lookback=_LOOKBACK_DELTA,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        series = _load_metric_full_series(
            store,
            instrument,
            params,
            n_obs=_DELTA_20D_REPORTS + _LOOKBACK_DELTA + 1,
        )
        if series is None:
            return 0.0
        result = _mode_delta_z(
            series,
            instrument,
            delta_reports=_DELTA_20D_REPORTS,
            lookback=_LOOKBACK_DELTA,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        series = _load_metric_full_series(store, instrument, params, n_obs=_LOOKBACK_PCT_12M + 1)
        if series is None:
            return 0.0
        pct = _mode_pct(series, instrument, _LOOKBACK_PCT_12M)
        if pct is None:
            return 0.0
        return _extreme_flag(pct, hard=(mode == "extreme_flag_hard"))

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "positioning.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    loaded = _load_metric_series(store, instrument, params)
    if loaded is None:
        return 0.0
    current, history = loaded
    pct = rank_percentile(current, history)
    if pct is None:
        return 0.0
    return round(pct / 100.0, 4)


# ---------------------------------------------------------------------------
# cot_z_score
# ---------------------------------------------------------------------------


@register("cot_z_score")
def cot_z_score(store: Any, instrument: str, params: dict) -> float:
    """Robust z-score (median+MAD) av MM net positioning, mappet til 0..1.

    Steg-mapping (default, kan overrides via ``z_thresholds``):
        z ≥ +2.0 → 1.0
        z ≥ +1.0 → 0.75
        z ≥ +0.5 → 0.6
        z ≥  0.0 → 0.5
        z ≥ −0.5 → 0.3
        ellers   → 0.0

    R4 (sub-fase 12.7): horisont-bevisst via ``params["mode"]`` per
    ADR-010 og ``docs/driver_horizon_pattern.md`` § 1.1. Default-output
    (mode=None) er bit-identisk med pre-R4 — kontraktuelt krav per
    § 5.3 (R4 = disiplin B, YAML uendret, score uendret).

    Mode-tabell (parallell til ``positioning_mm_pct`` siden begge
    leser MM net-serien fra samme COT-data):
    - ``None`` (default): z-score-trapp som over.
    - ``"pct_12m"``: rank-percentile av MM net over 52-rapport-vindu.
    - ``"pct_36m"``: rank-percentile over 156-rapport-vindu, fall-back
      til pct_12m + log ved utilstrekkelig historikk.
    - ``"delta_5d_z"``: z-score-trapp av 1-rapport-delta i MM net
      (~7d natural for ukentlig COT). Operates på en ANNEN underliggende
      serie enn default (delta vs rå MM net) — verdiene er ikke
      kommensurable, men begge er bull-of-instrument-konvensjon.
    - ``"delta_20d_z"``: 4-rapport-delta (~28d natural).
    - ``"extreme_flag_hard"``: 1.0 ved pct_12m ≥ 0.98 eller ≤ 0.02.
    - ``"extreme_flag_soft"``: 1.0 ved pct_12m ≥ 0.95 eller ≤ 0.05.

    Default ↔ mode-relasjon: default returnerer en z-score-trapp av
    rå MM net (current vs history). ``delta_*_z``-modes returnerer
    z-score-trapp av delta-aggregat på samme underliggende MM net.
    Modes er IKKE "delta av default-output" — de er parallelle
    aggregeringer.

    Defensiv 0.0-retur ved manglende COT-data, MAD=0, eller
    utilstrekkelig historikk. Ukjent mode → log warning + fall-back
    til default.
    """
    # ADR-010: les _horizon for fremtidig bruk. R4-kontrakt: ikke endre
    # default-output basert på _horizon.
    _horizon = params.get("_horizon")
    mode = params.get("mode")

    if mode is None:
        return _cot_z_score_default(store, instrument, params)

    # Eksplisitt mode-håndtering (R4-utvidelse, parallell til positioning_mm_pct).
    if mode == "pct_12m":
        series = _load_metric_full_series(store, instrument, params, n_obs=_LOOKBACK_PCT_12M + 1)
        if series is None:
            return 0.0
        result = _mode_pct(series, instrument, _LOOKBACK_PCT_12M)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        series = _load_metric_full_series(store, instrument, params, n_obs=_LOOKBACK_PCT_36M + 1)
        if series is None:
            return 0.0
        result = _mode_pct(series, instrument, _LOOKBACK_PCT_36M)
        if result is None:
            _log.info(
                "cot_z_score.pct_36m_fallback_to_12m",
                instrument=instrument,
                available_obs=len(series),
                required=_LOOKBACK_PCT_36M + 1,
            )
            result = _mode_pct(series, instrument, _LOOKBACK_PCT_12M)
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        series = _load_metric_full_series(
            store,
            instrument,
            params,
            n_obs=_DELTA_5D_REPORTS + _LOOKBACK_DELTA + 1,
        )
        if series is None:
            return 0.0
        result = _mode_delta_z(
            series,
            instrument,
            delta_reports=_DELTA_5D_REPORTS,
            lookback=_LOOKBACK_DELTA,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        series = _load_metric_full_series(
            store,
            instrument,
            params,
            n_obs=_DELTA_20D_REPORTS + _LOOKBACK_DELTA + 1,
        )
        if series is None:
            return 0.0
        result = _mode_delta_z(
            series,
            instrument,
            delta_reports=_DELTA_20D_REPORTS,
            lookback=_LOOKBACK_DELTA,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        series = _load_metric_full_series(store, instrument, params, n_obs=_LOOKBACK_PCT_12M + 1)
        if series is None:
            return 0.0
        pct = _mode_pct(series, instrument, _LOOKBACK_PCT_12M)
        if pct is None:
            return 0.0
        return _extreme_flag(pct, hard=(mode == "extreme_flag_hard"))

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "cot_z_score.unknown_mode_falling_back_to_default",
        instrument=instrument,
        mode=mode,
    )
    return _cot_z_score_default(store, instrument, params)


def _cot_z_score_default(store: Any, instrument: str, params: dict) -> float:
    """Pre-R4-default-bane for cot_z_score, isolert for å garantere bit-
    identisk output uavhengig av om mode-dispatcher rammer fall-back-grenen
    eller ikke."""
    loaded = _load_metric_series(store, instrument, params)
    if loaded is None:
        return 0.0
    current, history = loaded

    z = rolling_z(current, history)
    if z is None:
        return 0.0

    thresholds = params.get("z_thresholds")
    if thresholds is None:
        steps = _DEFAULT_Z_THRESHOLDS
    else:
        # Brukers-overstyrt: forvent liste av (terskel, score)-tupler
        # eller dict {"+2": 1.0, ...}-form. Aksepter begge for fleksibilitet.
        if isinstance(thresholds, dict):
            steps_list: list[tuple[float, float]] = []
            for k, v in thresholds.items():
                key_str = str(k).replace("+", "")
                steps_list.append((float(key_str), float(v)))
            steps = tuple(sorted(steps_list, key=lambda t: -t[0]))
        else:
            steps = tuple(thresholds)

    for threshold, score in steps:
        if z >= threshold:
            return float(score)
    return 0.0


# ---------------------------------------------------------------------------
# cot_ice_mm_pct (sub-fase 12.5+ session 106)
# ---------------------------------------------------------------------------


def _load_ice_metric_series(
    store: Any,
    params: dict,
) -> tuple[float, list[float]] | None:
    """Datastrøm-loader for ICE-COT, parallell til ``_load_metric_series``.

    Forskjellen fra CFTC-versjonen: ``contract`` leses fra ``params``
    (YAML-driven), ikke fra instrument-config. ICE-canonical contract-
    strenger er ``"ice brent crude"`` / ``"ice gasoil"`` / ``"ice ttf gas"``.

    Returnerer ``(current, history)`` eller ``None`` ved feil.
    """
    contract = params.get("contract")
    if not contract:
        _log.warning("cot_ice.no_contract_in_params params=%s", params)
        return None

    lookback = int(params.get("lookback_weeks", _DEFAULT_LOOKBACK))
    metric = str(params.get("metric", _DEFAULT_METRIC))

    try:
        df = store.get_cot_ice(contract, last_n=lookback + 1)
    except KeyError:
        _log.debug("cot_ice.data_missing contract=%s", contract)
        return None
    except Exception as exc:
        _log.warning("cot_ice.fetch_failed contract=%s error=%s", contract, exc)
        return None

    series = _compute_metric(df, metric)
    if series is None:
        _log.warning("cot_ice.unknown_metric contract=%s metric=%s", contract, metric)
        return None

    series = series.dropna()
    if len(series) < MIN_OBS_FOR_PCTILE + 1:
        _log.debug(
            "cot_ice.short_history contract=%s n=%d required=%d",
            contract,
            len(series),
            MIN_OBS_FOR_PCTILE + 1,
        )
        return None

    current = float(series.iloc[-1])
    history = [float(v) for v in series.iloc[:-1]]
    return current, history


def _load_ice_metric_full_series(
    store: Any,
    params: dict,
    *,
    n_obs: int,
) -> pd.Series | None:
    """Hent ICE-COT-metric-serie med eksplisitt antall obs (inkl. current).

    Parallell til ``_load_metric_full_series`` for CFTC-COT. Returnerer
    pd.Series sortert chronologisk eller None ved feil. Brukes av R4-
    modes som trenger full serie (delta-modes må bygge diff-serien)
    eller utvidet historikk (pct_36m).
    """
    contract = params.get("contract")
    if not contract:
        _log.warning("cot_ice.no_contract_in_params params=%s", params)
        return None

    metric = str(params.get("metric", _DEFAULT_METRIC))

    try:
        df = store.get_cot_ice(contract, last_n=n_obs)
    except KeyError:
        _log.debug("cot_ice.data_missing contract=%s", contract)
        return None
    except Exception as exc:
        _log.warning("cot_ice.fetch_failed contract=%s error=%s", contract, exc)
        return None

    series = _compute_metric(df, metric)
    if series is None:
        _log.warning("cot_ice.unknown_metric contract=%s metric=%s", contract, metric)
        return None

    series = series.dropna()
    if series.empty:
        return None
    return series


@register("cot_ice_mm_pct")
def cot_ice_mm_pct(store: Any, instrument: str, params: dict) -> float:
    """Rank-percentile av MM net positioning fra ICE COT, normalisert til 0..1.

    Parallell til ``positioning_mm_pct`` men leser fra ``store.get_cot_ice``
    (ICE Futures Europe COT) i stedet for ``store.get_cot`` (CFTC).
    Brukes for instrumenter listet på ICE — Brent Crude (primær COT-kilde,
    siden Brent er ICE-listet), Gasoil og TTF Natural Gas (overlay til
    CFTC-COT-driver for cross-validering).

    Params:
        contract (REQUIRED): ICE-canonical streng. F.eks. ``"ice brent crude"``,
            ``"ice gasoil"``, ``"ice ttf gas"``. Kommer fra YAML-wiring,
            ikke fra instrument-config (siden bedrock per i dag har
            ``cot_contract`` knyttet til CFTC).
        lookback_weeks: rolling-vindu (default 52). Når ``mode`` er satt
            overstyres lookback_weeks av mode-spesifikt vindu (52 for
            pct_12m/delta_*_z, 156 for pct_36m).
        metric: ``"mm_net"`` (default) eller ``"mm_net_pct"``.
        mode: feature-velger per ADR-010. ``None``/utelatt (default) =
            dagens output (bit-identisk pre-R4). ``"pct_12m"`` /
            ``"pct_36m"`` / ``"delta_5d_z"`` / ``"delta_20d_z"`` /
            ``"extreme_flag_hard"`` / ``"extreme_flag_soft"`` per
            docs/driver_horizon_pattern.md § 1.1. Mode-implementasjonen
            gjenbruker helpers fra positioning_mm_pct (samme modul).
        _horizon: engine-injisert kontekst-key per ADR-010. Lest men
            ikke brukt til å endre output i R4 (per § 5.3 R4-kontrakt).

    Returnerer:
    - 1.0 ved ekstrem MM long (top-percentile)
    - 0.5 ved median posisjonering
    - 0.0 ved ekstrem MM short eller manglende data

    Defensiv: alle feil → 0.0 + log, ingen exception.
    """
    # ADR-010: les _horizon for fremtidig bruk. R4-kontrakt: ikke endre
    # default-output basert på _horizon.
    _horizon = params.get("_horizon")
    mode = params.get("mode")

    if mode is None:
        return _cot_ice_mm_pct_default(store, params)

    # Eksplisitt mode-håndtering (R4-utvidelse).
    if mode == "pct_12m":
        series = _load_ice_metric_full_series(store, params, n_obs=_LOOKBACK_PCT_12M + 1)
        if series is None:
            return 0.0
        result = _mode_pct(series, params.get("contract", "ice"), _LOOKBACK_PCT_12M)
        return round(result, 4) if result is not None else 0.0

    if mode == "pct_36m":
        series = _load_ice_metric_full_series(store, params, n_obs=_LOOKBACK_PCT_36M + 1)
        if series is None:
            return 0.0
        result = _mode_pct(series, params.get("contract", "ice"), _LOOKBACK_PCT_36M)
        if result is None:
            _log.info(
                "cot_ice.pct_36m_fallback_to_12m",
                contract=params.get("contract"),
                available_obs=len(series),
                required=_LOOKBACK_PCT_36M + 1,
            )
            result = _mode_pct(series, params.get("contract", "ice"), _LOOKBACK_PCT_12M)
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_5d_z":
        series = _load_ice_metric_full_series(
            store,
            params,
            n_obs=_DELTA_5D_REPORTS + _LOOKBACK_DELTA + 1,
        )
        if series is None:
            return 0.0
        result = _mode_delta_z(
            series,
            params.get("contract", "ice"),
            delta_reports=_DELTA_5D_REPORTS,
            lookback=_LOOKBACK_DELTA,
        )
        return round(result, 4) if result is not None else 0.0

    if mode == "delta_20d_z":
        series = _load_ice_metric_full_series(
            store,
            params,
            n_obs=_DELTA_20D_REPORTS + _LOOKBACK_DELTA + 1,
        )
        if series is None:
            return 0.0
        result = _mode_delta_z(
            series,
            params.get("contract", "ice"),
            delta_reports=_DELTA_20D_REPORTS,
            lookback=_LOOKBACK_DELTA,
        )
        return round(result, 4) if result is not None else 0.0

    if mode in ("extreme_flag_hard", "extreme_flag_soft"):
        series = _load_ice_metric_full_series(store, params, n_obs=_LOOKBACK_PCT_12M + 1)
        if series is None:
            return 0.0
        pct = _mode_pct(series, params.get("contract", "ice"), _LOOKBACK_PCT_12M)
        if pct is None:
            return 0.0
        return _extreme_flag(pct, hard=(mode == "extreme_flag_hard"))

    # Ukjent mode: log + fall-back til default.
    _log.warning(
        "cot_ice.unknown_mode_falling_back_to_default",
        contract=params.get("contract"),
        mode=mode,
    )
    return _cot_ice_mm_pct_default(store, params)


def _cot_ice_mm_pct_default(store: Any, params: dict) -> float:
    """Pre-R4-default-bane for cot_ice_mm_pct, isolert for å garantere
    bit-identisk output uavhengig av om mode-dispatcher rammer fall-back-
    grenen eller ikke."""
    loaded = _load_ice_metric_series(store, params)
    if loaded is None:
        return 0.0
    current, history = loaded

    pct = rank_percentile(current, history)
    if pct is None:
        return 0.0

    return round(pct / 100.0, 4)


# ---------------------------------------------------------------------------
# Euronext COT (sub-fase 12.5+ session 110)
# ---------------------------------------------------------------------------


def _load_euronext_metric_series(
    store: Any,
    params: dict,
) -> tuple[float, list[float]] | None:
    """Datastrøm-loader for Euronext-COT, parallell til ICE-versjonen.

    `contract` er bedrock-canonical (``"euronext milling wheat"``,
    ``"euronext corn"``, ``"euronext canola"``) og leses fra params.
    Returnerer ``(current, history)`` eller None ved feil.
    """
    contract = params.get("contract")
    if not contract:
        _log.warning("cot_euronext.no_contract_in_params params=%s", params)
        return None

    lookback = int(params.get("lookback_weeks", _DEFAULT_LOOKBACK))
    metric = str(params.get("metric", _DEFAULT_METRIC))

    try:
        df = store.get_cot_euronext(contract, last_n=lookback + 1)
    except KeyError:
        _log.debug("cot_euronext.data_missing contract=%s", contract)
        return None
    except Exception as exc:
        _log.warning("cot_euronext.fetch_failed contract=%s error=%s", contract, exc)
        return None

    series = _compute_metric(df, metric)
    if series is None:
        _log.warning("cot_euronext.unknown_metric contract=%s metric=%s", contract, metric)
        return None

    series = series.dropna()
    if len(series) < MIN_OBS_FOR_PCTILE + 1:
        _log.debug(
            "cot_euronext.short_history contract=%s n=%d required=%d",
            contract,
            len(series),
            MIN_OBS_FOR_PCTILE + 1,
        )
        return None

    current = float(series.iloc[-1])
    history = [float(v) for v in series.iloc[:-1]]
    return current, history


@register("cot_euronext_mm_pct")
def cot_euronext_mm_pct(store: Any, instrument: str, params: dict) -> float:
    """Rank-percentile av MM net positioning fra Euronext COT, normalisert til 0..1.

    Parallell til ``cot_ice_mm_pct`` men leser fra ``store.get_cot_euronext``
    (Euronext MiFID II COT). Brukes som EU-overlay for grain-kontrakter
    (Wheat, Corn) — co-driver til CFTC ``positioning_mm_pct``.

    Params:
        contract (REQUIRED): bedrock-canonical streng. ``"euronext milling
            wheat"``, ``"euronext corn"``, eller ``"euronext canola"``.
        lookback_weeks: rolling-vindu (default 52).
        metric: ``"mm_net"`` (default) eller ``"mm_net_pct"``.

    Returnerer:
    - 1.0 ved ekstrem MM long
    - 0.5 ved median posisjonering
    - 0.0 ved ekstrem MM short eller manglende data

    Defensiv: alle feil → 0.0 + log.
    """
    loaded = _load_euronext_metric_series(store, params)
    if loaded is None:
        return 0.0
    current, history = loaded

    pct = rank_percentile(current, history)
    if pct is None:
        return 0.0

    return round(pct / 100.0, 4)


__all__ = [
    "cot_euronext_mm_pct",
    "cot_ice_mm_pct",
    "cot_z_score",
    "positioning_mm_pct",
]
