# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false
# pandas-stubs false-positives — se data/store.py for kontekst.

"""Analog-familie drivere (Fase 10 ADR-005 B5, session 60).

Drivere som bruker K-NN over historiske dim-verdier per asset-klasse
(per PLAN § 6.5) til å score nåtidige signaler. Bygger på
`bedrock.data.analog.find_analog_cases` fra session 59.

To drivere implementert:

- `analog_hit_rate`: andelen av K nærmeste historiske naboer som har
  forward_return ≥ outcome_threshold_pct. Returnerer 0..1.
- `analog_avg_return`: gjennomsnittlig forward_return blant K naboer,
  mappet til 0..1-score via terskel-trapp (unidirectional bull —
  matcher trend.py/currency.py-konvensjonen).

Begge drivere er defensive per `engine/drivers/__init__.py`-kontrakten:
feil i extractor/data-oppslag returnerer 0.0 + log, ikke exception.

Driver-params (felles):
- `asset_class`: påkrevd. Må matche en nøkkel i `ASSET_CLASS_DIMS`.
- `k`: antall naboer (default 5)
- `horizon_days`: forward-vindu (default 30)
- `min_history_days`: filter (default 365)
- `dim_weights`: optional `dict[str, float]` for weighted Euclidean
- `instruments_dir`: optional override for YAML-lookup (default `config/instruments`)

Driver-spesifikke params:
- `analog_hit_rate.outcome_threshold_pct`: terskel for "hit" (default 3.0)
- `analog_avg_return.score_thresholds`: optional terskel-trapp som dict
  `{"+5": 1.0, "+2": 0.7, "0": 0.4}` — default brukes hvis utelatt

Per ADR-005 B5: hit-terskel + horizon + K er driver-config og kan
overstyres per asset-klasse via `config/defaults/`-inheritance uten
å endre driver-kode.
"""

from __future__ import annotations

from typing import Any

import structlog

from bedrock.data.analog import (
    ASSET_CLASS_DIMS,
    InsufficientHistoryError,
    MissingDataError,
    MissingExtractorError,
    extract_query_from_latest,
    find_analog_cases,
)
from bedrock.engine.drivers import register

# `find_instrument` importeres LAT inne i `_knn` for å unngå sirkulær
# import: cli._instrument_lookup → config.instruments → engine.engine →
# engine.drivers → engine.drivers.analog (her).

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Felles helper: hent K-NN-resultat fra params
# ---------------------------------------------------------------------------


def _knn(store: Any, instrument: str, params: dict) -> tuple[list[dict] | None, str]:
    """Felles K-NN-pipeline for begge drivere.

    Returnerer (rows, error_msg). `rows` er liste av dict med felter
    `forward_return_pct` og `max_drawdown_pct` for de K nærmeste, eller
    None ved feil. `error_msg` brukes til logging av drivers som returnerer 0.0.

    Defensiv: alle exceptions fra config-lookup, extractor-feil, eller
    K-NN-feil mappes til (None, msg) — driver returnerer 0.0 og logger.
    """
    asset_class = params.get("asset_class")
    if not asset_class:
        return None, "missing_asset_class"
    if asset_class not in ASSET_CLASS_DIMS:
        return None, f"unknown_asset_class={asset_class!r}"

    k = int(params.get("k", 5))
    horizon_days = int(params.get("horizon_days", 30))
    min_history_days = int(params.get("min_history_days", 365))
    dim_weights = params.get("dim_weights")
    instruments_dir = params.get("instruments_dir", "config/instruments")

    # Slå opp instrument-config (extractors trenger cot_contract,
    # weather_region etc. fra meta). Late import for å unngå sirkulær.
    from bedrock.cli._instrument_lookup import find_instrument

    try:
        cfg = find_instrument(instrument, instruments_dir=instruments_dir)
    except Exception as exc:
        return None, f"find_instrument failed: {exc}"
    meta = cfg.instrument

    # Bygg query fra ferskeste obs (skip_missing slik at vi ikke
    # krasjer på ennå-ikke-backfilte dim som vix_regime)
    try:
        query = extract_query_from_latest(store, meta, asset_class, skip_missing=True)
    except Exception as exc:
        return None, f"extract_query failed: {exc}"

    if not query:
        return None, "no_dims_available"

    # Kjør K-NN
    try:
        result = find_analog_cases(
            store,
            instrument,
            meta,
            asset_class,
            query,
            k=k,
            dim_weights=dim_weights,
            horizon_days=horizon_days,
            min_history_days=min_history_days,
        )
    except (MissingDataError, MissingExtractorError, InsufficientHistoryError) as exc:
        return None, f"find_analog_cases data-issue: {exc}"
    except Exception as exc:
        return None, f"find_analog_cases unexpected: {exc}"

    if result.empty:
        return None, "no_neighbors"

    # Konverter til liste av dict for letter prosessering
    rows = result[["forward_return_pct", "max_drawdown_pct"]].to_dict("records")
    return rows, ""


# ---------------------------------------------------------------------------
# analog_hit_rate
# ---------------------------------------------------------------------------


@register("analog_hit_rate")
def analog_hit_rate(store: Any, instrument: str, params: dict) -> float:
    """Andelen av K nærmeste naboer der forward_return krysser terskelen.

    Returnerer 0..1 direkte. Direction-aware (session 100, ADR-006
    spesialtilfeller):

    - BUY: hits = forward_return ≥ +outcome_threshold_pct
    - SELL: hits = forward_return ≤ -outcome_threshold_pct

    Engine setter `_direction` i params (BUY/SELL); default BUY.
    Forutsetter at family har `polarity: neutral` i YAML — driveren
    håndterer asymmetrien selv (ikke 1-x-flip på engine-siden).

    Per ADR-005 B5: terskel er driver-config, ikke lagret i data.
    """
    threshold = float(params.get("outcome_threshold_pct", 3.0))
    direction = str(params.get("_direction", "buy")).lower()

    rows, err = _knn(store, instrument, params)
    if rows is None:
        _log.debug("analog_hit_rate.skip", instrument=instrument, reason=err)
        return 0.0

    n = len(rows)
    if direction == "sell":
        hits = sum(1 for r in rows if r["forward_return_pct"] <= -threshold)
    else:
        hits = sum(1 for r in rows if r["forward_return_pct"] >= threshold)
    return hits / n


# ---------------------------------------------------------------------------
# analog_avg_return
# ---------------------------------------------------------------------------


_DEFAULT_AVG_RETURN_THRESHOLDS: list[tuple[float, float]] = [
    # (avg_return_threshold_pct, score) — sorteres descending på threshold,
    # første treff vinner. Symmetrisk for negative er ikke meningsfull her;
    # driveren er unidirectional bull, så avg < 0 → 0.0.
    (5.0, 1.0),
    (3.0, 0.8),
    (2.0, 0.65),
    (1.0, 0.5),
    (0.0, 0.4),  # marginalt positiv = svak edge
]
"""Default mapping: avg_return → driver-score for `analog_avg_return`."""


@register("analog_avg_return")
def analog_avg_return(store: Any, instrument: str, params: dict) -> float:
    """Gjennomsnittlig forward_return blant K naboer mappet til 0..1.

    Direction-aware (session 100, ADR-006 spesialtilfeller):
    Engine propagerer `_direction` (BUY/SELL) i params. For SELL flippes
    fortegn på avg-return før threshold-mapping, slik at terskel-trappen
    måler "hvor negativt forward-return har vært" (= bull SELL).

    Param `direction: "direct"|"invert"` (eldre konvensjon) overstyrer
    `_direction` for backwards-kompatibilitet.

    Mapping (default — beholdes for begge retninger; "≥ +X%" tolkes som
    "≥ +X% i preferert retning"):
    - avg ≥ +5%  → 1.0
    - avg ≥ +3%  → 0.8
    - avg ≥ +2%  → 0.65
    - avg ≥ +1%  → 0.5
    - avg ≥ 0%   → 0.4 (marginalt positiv)
    - avg < 0%   → 0.0 (negativ historikk)
    """
    explicit = params.get("direction")  # eldre param, hvis satt overstyrer
    if explicit is not None and explicit not in ("direct", "invert"):
        _log.warning(
            "analog_avg_return.unknown_direction",
            instrument=instrument,
            direction=explicit,
        )
        return 0.0

    thresholds = _resolve_thresholds(params.get("score_thresholds"))

    rows, err = _knn(store, instrument, params)
    if rows is None:
        _log.debug("analog_avg_return.skip", instrument=instrument, reason=err)
        return 0.0

    avg = sum(r["forward_return_pct"] for r in rows) / len(rows)

    # Bestem invertering: eldre `direction: invert` har prioritet, ellers
    # bruk engine-propagert `_direction` (BUY = direct, SELL = invert).
    if explicit == "invert":
        invert = True
    elif explicit == "direct":
        invert = False
    else:
        engine_dir = str(params.get("_direction", "buy")).lower()
        invert = engine_dir == "sell"

    if invert:
        avg = -avg

    return _map_avg_to_score(avg, thresholds)


def _resolve_thresholds(
    raw: dict[str, float] | None,
) -> list[tuple[float, float]]:
    """Konverter param-dict til sortert (threshold, score)-liste.

    Param-format eksempel: `{"+5.0": 1.0, "+2.0": 0.7, "0.0": 0.4}`.
    Default brukes hvis raw er None eller tom.
    """
    if not raw:
        return _DEFAULT_AVG_RETURN_THRESHOLDS

    out: list[tuple[float, float]] = []
    for k, v in raw.items():
        try:
            out.append((float(k), float(v)))
        except ValueError:
            _log.warning("analog_avg_return.bad_threshold", key=k, value=v)
            continue
    # Sortér descending på threshold — første treff vinner i mapping
    return sorted(out, key=lambda t: t[0], reverse=True)


def _map_avg_to_score(avg: float, thresholds: list[tuple[float, float]]) -> float:
    """Map avg-return til 0..1-score via terskel-trapp.

    Første terskel der `avg >= threshold` vinner. Hvis avg er under alle
    tersklene returneres 0.0 (negativ historikk = ingen edge for bull).
    """
    for threshold, score in thresholds:
        if avg >= threshold:
            return score
    return 0.0
