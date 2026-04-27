"""Positioning-familie drivere (Sub-fase 12.5 session 70).

Erstatter ``sma200_align``-placeholder i positioning-familien. Bruker
COT-data fra ``DataStore.get_cot()`` til å beregne hvor ekstrem
managed-money-positioneringen er relativt til historikken.

To drivere implementert:

- ``positioning_mm_pct``: rank-percentile (0-100) av MM net positioning
  over rolling window. Mappes til 0..1.
- ``cot_z_score``: robust z-score (median+MAD) av MM net positioning,
  mappet til 0..1 via terskel-trapp matching ``momentum_z``-konvensjonen.

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
- ``metric``: ``"mm_net"`` (default), eller ``"mm_net_pct"`` for å
  normalisere mot open_interest. ``mm_net_pct`` reduserer scale-bias
  når OI vokser/krymper kraftig (anbefalt for instrumenter med stor
  OI-variasjon).

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


# Default mapping for cot_z_score: matcher momentum_z-trappen i trend.py
# slik at familier som blander z-baserte drivere får konsistent skalering.
_DEFAULT_Z_THRESHOLDS: tuple[tuple[float, float], ...] = (
    (2.0, 1.0),
    (1.0, 0.75),
    (0.5, 0.6),
    (0.0, 0.5),
    (-0.5, 0.3),
)


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


@register("positioning_mm_pct")
def positioning_mm_pct(store: Any, instrument: str, params: dict) -> float:
    """Rank-percentile av MM net positioning, normalisert til 0..1.

    Returnerer:
    - 1.0 ved ekstrem MM long (top-percentile)
    - 0.5 ved median posisjonering
    - 0.0 ved ekstrem MM short (bunn-percentile)

    Defensiv 0.0-retur ved manglende COT-data, ukjent contract eller
    utilstrekkelig historikk.
    """
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

    Defensiv 0.0-retur ved manglende COT-data, MAD=0 eller utilstrekkelig
    historikk.
    """
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
        lookback_weeks: rolling-vindu (default 52).
        metric: ``"mm_net"`` (default) eller ``"mm_net_pct"``.

    Returnerer:
    - 1.0 ved ekstrem MM long (top-percentile)
    - 0.5 ved median posisjonering
    - 0.0 ved ekstrem MM short eller manglende data

    Defensiv: alle feil → 0.0 + log, ingen exception.
    """
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
