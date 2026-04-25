"""Analog-matching: K-NN over historiske dim-verdier (ADR-005, Fase 10 session 59).

Per PLAN § 6.5: for hver asset-klasse defineres et fast sett av dimensjoner
(VIX, real-yield-endring, DXY-endring, COT-posisjonering osv.). For et nytt
signal beregner vi nåverdiene av disse dimensjonene, normaliserer dem mot
hele historikken, og finner K nærmeste historiske datoer (weighted Euclidean).
For hver nabo har vi pre-beregnet `forward_return_pct` + `max_drawdown_pct`
(ADR-005 B3) — outputten gir analog-driveren grunnlag for hit-rate og
snitt-return-narrativ.

Modulens ansvar:
- `ASSET_CLASS_DIMS` — § 6.5-tabellen slavisk. Brudd flagges, ikke stille
  utvidet (per audit § 5.1 + bruker-instruks Q2).
- `DIM_EXTRACTORS` — for de dim-navn vi har data til (6 av 12 etter Fase 10
  session 58 backfill). Resten kaster `MissingExtractorError` slik at
  driver-laget i session 60 kan håndtere gracefully.
- `extract_query_from_latest` — bygg `query_dims` fra ferskeste obs.
- `find_analog_cases` — selve K-NN.

ADR-005-tillegg (session 59): `find_analog_cases` ble frittstående
funksjon her istedenfor `DataStore`-metode (per ADR B4). Begrunnelse:
extractors trenger `InstrumentMetadata` (cot_contract, weather_region),
og å la DataStore importere fra config-laget hadde innført unødvendig
kobling. Funksjonen tar `store` + `meta` eksplisitt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from bedrock.config.instruments import InstrumentMetadata
    from bedrock.data.store import DataStore


# ---------------------------------------------------------------------------
# § 6.5 dim-tabell (slavisk)
# ---------------------------------------------------------------------------


ASSET_CLASS_DIMS: dict[str, list[str]] = {
    "metals": ["vix_regime", "real_yield_chg5d", "dxy_chg5d", "cot_mm_pct"],
    "fx": ["rate_differential_chg", "vix_regime", "dxy_chg5d", "term_spread"],
    "energy": [
        "backwardation",
        "supply_disruption_level",
        "dxy_chg5d",
        "cot_commercial_pct",
    ],
    "grains": [
        "weather_stress_key_region",
        "enso_regime",
        "conab_yoy",
        "dxy_chg5d",
    ],
    "softs": ["weather_stress", "enso_regime", "unica_mix_change", "brl_chg5d"],
}
"""Per PLAN § 6.5. Brudd flagges via MissingExtractorError, ikke skjult."""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MissingExtractorError(KeyError):
    """En dim har ingen extractor — typisk fordi data ikke er backfilt ennå
    (VIX, BRL, UNICA etc. — se audit § 5)."""


class MissingDataError(RuntimeError):
    """Extractor finnes, men dataen i DataStore er tom/utilgjengelig."""


class InsufficientHistoryError(RuntimeError):
    """For få overlappende ref_dates til å gjøre meningsfull K-NN."""


# ---------------------------------------------------------------------------
# Extractors per dim
# ---------------------------------------------------------------------------

DimExtractor = Callable[["DataStore", "InstrumentMetadata"], pd.Series]
"""Hver extractor returnerer pd.Series indeksert på datetime, daglig granularitet
hvis mulig (forward-fill brukt for ukentlig/månedlig kilder)."""


def _extract_dxy_chg5d(store: DataStore, meta: InstrumentMetadata) -> pd.Series:
    """5-dagers prosent-endring i DTWEXBGS (broad dollar-indeks)."""
    s = store.get_fundamentals("DTWEXBGS").dropna()
    out = (s.pct_change(5) * 100.0).dropna()
    if out.empty:
        raise MissingDataError("DTWEXBGS pct_change(5) ga tom serie")
    out.name = "dxy_chg5d"
    return out


def _extract_real_yield_chg5d(store: DataStore, meta: InstrumentMetadata) -> pd.Series:
    """5-dagers endring i real-yield (DGS10 - T10YIE), i prosentpoeng."""
    dgs10 = store.get_fundamentals("DGS10")
    t10yie = store.get_fundamentals("T10YIE")
    real = (dgs10 - t10yie).dropna()
    out = real.diff(5).dropna()
    if out.empty:
        raise MissingDataError("real_yield diff(5) ga tom serie")
    out.name = "real_yield_chg5d"
    return out


def _extract_term_spread(store: DataStore, meta: InstrumentMetadata) -> pd.Series:
    """10Y-2Y treasury-spread."""
    dgs10 = store.get_fundamentals("DGS10")
    dgs2 = store.get_fundamentals("DGS2")
    out = (dgs10 - dgs2).dropna()
    if out.empty:
        raise MissingDataError("DGS10-DGS2 spread ga tom serie")
    out.name = "term_spread"
    return out


def _extract_cot_mm_pct(store: DataStore, meta: InstrumentMetadata) -> pd.Series:
    """Managed-money-long som prosent av total mm-posisjon. Forward-fill
    fra ukentlig CFTC-rapport til daglig."""
    if not meta.cot_contract:
        raise MissingDataError(f"Instrument {meta.id!r} mangler cot_contract")
    df = store.get_cot(meta.cot_contract, report="disaggregated")
    if df.empty:
        raise MissingDataError(f"COT for {meta.cot_contract!r} ga tom DataFrame")
    total = df["mm_long"] + df["mm_short"]
    pct = (df["mm_long"] / total.replace(0, np.nan) * 100.0).fillna(50.0)
    s = pd.Series(pct.values, index=pd.to_datetime(df["report_date"]))
    # Forward-fill til daglig (CFTC publiserer ukentlig fredag)
    daily = s.resample("D").ffill()
    daily.name = "cot_mm_pct"
    return daily


def _extract_enso_regime(store: DataStore, meta: InstrumentMetadata) -> pd.Series:
    """NOAA ONI-verdi, månedlig forward-filled til daglig."""
    s = store.get_fundamentals("NOAA_ONI")
    if s.empty:
        raise MissingDataError("NOAA_ONI ga tom serie")
    daily = s.resample("D").ffill()
    daily.name = "enso_regime"
    return daily


def _extract_weather_stress(store: DataStore, meta: InstrumentMetadata) -> pd.Series:
    """Vær-stress (negativ water_bal, så høyere = mer stress) for
    instrumentets weather_region. Månedlig → daglig forward-fill."""
    if not meta.weather_region:
        raise MissingDataError(f"Instrument {meta.id!r} mangler weather_region")
    df = store.get_weather_monthly(meta.weather_region)
    if df.empty or df["water_bal"].isna().all():
        raise MissingDataError(
            f"weather_monthly for region {meta.weather_region!r} har ingen water_bal"
        )
    # Konverter "YYYY-MM" → første-i-måneden timestamp
    months = pd.to_datetime(df["month"] + "-01")
    stress = -df["water_bal"]  # negativ vannbalanse = stress
    s = pd.Series(stress.values, index=months).dropna()
    daily = s.resample("D").ffill()
    daily.name = "weather_stress"
    return daily


# Dim-navn → extractor. Mangelfulle dim (VIX, BRL, UNICA, etc.) har
# ingen entry og kaster MissingExtractorError ved oppslag — driver
# håndterer (session 60).
DIM_EXTRACTORS: dict[str, DimExtractor] = {
    "dxy_chg5d": _extract_dxy_chg5d,
    "real_yield_chg5d": _extract_real_yield_chg5d,
    "term_spread": _extract_term_spread,
    "cot_mm_pct": _extract_cot_mm_pct,
    "enso_regime": _extract_enso_regime,
    "weather_stress_key_region": _extract_weather_stress,
    "weather_stress": _extract_weather_stress,  # softs-alias for samme extractor
}


def get_extractor(dim: str) -> DimExtractor:
    """Slå opp extractor for et dim-navn. Kaster `MissingExtractorError`
    hvis dim ikke har implementasjon (typisk fordi data ikke er backfilt)."""
    try:
        return DIM_EXTRACTORS[dim]
    except KeyError as exc:
        raise MissingExtractorError(
            f"No extractor for dim {dim!r}. "
            f"Implemented: {sorted(DIM_EXTRACTORS)}. "
            f"Add to DIM_EXTRACTORS in bedrock.data.analog after backfilling source."
        ) from exc


# ---------------------------------------------------------------------------
# Query-bygger
# ---------------------------------------------------------------------------


def extract_query_from_latest(
    store: DataStore,
    meta: InstrumentMetadata,
    asset_class: str,
    *,
    dims: list[str] | None = None,
    skip_missing: bool = True,
) -> dict[str, float]:
    """Bygg `query_dims`-dict fra ferskeste observasjon per dim.

    `dims` default = ASSET_CLASS_DIMS[asset_class]. Hvis et dim mangler
    extractor (eller data er tom), oppførsel styres av `skip_missing`:
    - True (default): hopp over og logg, returner partial dict
    - False: kast første feilen som popper opp

    Returnerer `{dim_name: latest_value}` med kun de dim som faktisk
    kunne hentes. Caller (driver) avgjør hvor strenge krav som stilles
    før K-NN kalles.
    """
    if dims is None:
        if asset_class not in ASSET_CLASS_DIMS:
            raise KeyError(f"Unknown asset_class: {asset_class!r}")
        dims = ASSET_CLASS_DIMS[asset_class]

    out: dict[str, float] = {}
    for dim in dims:
        try:
            extractor = get_extractor(dim)
            series = extractor(store, meta)
        except (MissingExtractorError, MissingDataError, KeyError):
            if skip_missing:
                continue
            raise
        out[dim] = float(series.iloc[-1])
    return out


# ---------------------------------------------------------------------------
# K-NN
# ---------------------------------------------------------------------------


@dataclass
class _DimMatrix:
    """Internal: aligned history + query for K-NN."""

    history: pd.DataFrame  # date index × dim columns (z-normalisert)
    query_norm: dict[str, float]  # dim → z-score
    weights: np.ndarray  # ordered same as columns


def _build_dim_matrix(
    store: DataStore,
    meta: InstrumentMetadata,
    query_dims: dict[str, float],
    dim_weights: dict[str, float] | None,
) -> _DimMatrix:
    """Hent historiske serier for hver dim i query_dims, align på dato,
    z-normaliser per kolonne, og z-normaliser query med samme mean/std."""
    series_map: dict[str, pd.Series] = {}
    for dim in query_dims:
        extractor = get_extractor(dim)
        s = extractor(store, meta)
        series_map[dim] = s

    # Outer-join på dato → DataFrame med NaN i dropouts
    df = pd.concat(series_map, axis=1).dropna()
    if df.empty:
        raise InsufficientHistoryError(
            "Etter join på dato har ingen rad full coverage av alle dim. "
            "Sjekk om DataStore har overlappende historikk."
        )

    # Z-normaliser per kolonne. Bruk ddof=0 for befolknings-std (vanlig i ML).
    means = df.mean()
    stds = df.std(ddof=0).replace(0.0, 1.0)  # unngå 0-divisjon for konstante dim
    history_norm = (df - means) / stds

    query_norm = {dim: (query_dims[dim] - means[dim]) / stds[dim] for dim in df.columns}

    if dim_weights is None:
        dim_weights = dict.fromkeys(df.columns, 1.0)
    weights = np.array([float(dim_weights.get(dim, 1.0)) for dim in df.columns])

    return _DimMatrix(history=history_norm, query_norm=query_norm, weights=weights)


def find_analog_cases(
    store: DataStore,
    instrument: str,
    meta: InstrumentMetadata,
    asset_class: str,
    query_dims: dict[str, float],
    *,
    k: int = 5,
    dim_weights: dict[str, float] | None = None,
    horizon_days: int = 30,
    min_history_days: int = 365,
) -> pd.DataFrame:
    """Finn K nærmeste historiske analoger for et instrument basert på
    weighted Euclidean distance over normaliserte dim-verdier.

    Per ADR-005 B4 (med tillegg dokumentert øverst i modulen):
    frittstående funksjon i `bedrock.data.analog`, ikke `DataStore`-
    metode.

    Args:
        store: DataStore-instansen
        instrument: Bedrock-instrument-ID (f.eks. "Gold")
        meta: InstrumentMetadata fra YAML — extractors leser cot_contract
            og weather_region herfra
        asset_class: brukes til § 6.5-validering av query_dims-nøkler.
            Hvis `query_dims` har dim utenfor ASSET_CLASS_DIMS[asset_class],
            kastes ValueError.
        query_dims: nåverdier per dim, typisk fra `extract_query_from_latest`
        k: antall naboer å returnere (default 5 per § 6.5)
        dim_weights: per-dim vekter for Euclidean. Default: uniform 1.0.
        horizon_days: matcher mot `analog_outcomes.horizon_days` (default 30)
        min_history_days: filtrer bort ref_dates yngre enn min_history_days
            etter eldste tilgjengelige observasjon — unngår at K-NN matcher
            mot perioder der dim-historikken ennå ikke har stabilisert seg.

    Returns:
        pd.DataFrame med kolonner `ref_date`, `similarity`,
        `forward_return_pct`, `max_drawdown_pct`. `similarity` er
        `1 / (1 + weighted_euclidean_distance)` — høyere er bedre,
        max 1.0 (perfekt match), monotont avtagende.
        Tom DataFrame hvis ingen kandidater (typisk: instrument
        mangler outcomes, eller for kort historikk).
    """
    # Validér query_dims mot § 6.5
    if asset_class not in ASSET_CLASS_DIMS:
        raise KeyError(f"Unknown asset_class: {asset_class!r}")
    expected = set(ASSET_CLASS_DIMS[asset_class])
    extra = set(query_dims) - expected
    if extra:
        raise ValueError(
            f"query_dims for asset_class={asset_class!r} contains dim(s) "
            f"outside § 6.5: {sorted(extra)}. Expected subset of: {sorted(expected)}"
        )
    if not query_dims:
        raise ValueError("query_dims is empty — nothing to match on")

    # Hent outcomes
    outcomes = store.get_outcomes(instrument, horizon_days=horizon_days)
    if outcomes.empty:
        return _empty_result()

    # Bygg dim-matrise (history + normalisert query)
    matrix = _build_dim_matrix(store, meta, query_dims, dim_weights)

    # Filter outcomes til ref_dates som har dim-coverage
    history_dates = matrix.history.index
    if len(history_dates) == 0:
        return _empty_result()

    earliest = history_dates.min() + pd.Timedelta(days=min_history_days)
    candidates = outcomes[outcomes["ref_date"] >= earliest].copy()
    if candidates.empty:
        return _empty_result()

    # Inner-join outcomes mot history-dates: kun ref_dates der vi har
    # full dim-vektor. Outcomes har timezone-bearing timestamps fra
    # prices-tabellen, mens dim-history er datoer. Normaliser til date
    # for matching.
    candidates["_match_date"] = candidates["ref_date"].dt.normalize().dt.tz_localize(None)
    history_norm_idx = matrix.history.copy()
    history_norm_idx.index = pd.to_datetime(history_norm_idx.index).tz_localize(None).normalize()
    aligned = candidates.merge(
        history_norm_idx,
        how="inner",
        left_on="_match_date",
        right_index=True,
    )
    if aligned.empty:
        return _empty_result()

    # Beregn weighted Euclidean
    dim_cols = list(matrix.query_norm.keys())
    history_arr = aligned[dim_cols].to_numpy()  # shape (n_candidates, n_dims)
    query_arr = np.array([matrix.query_norm[d] for d in dim_cols])  # shape (n_dims,)
    diff = history_arr - query_arr  # shape (n, d)
    weighted_sq = (diff**2) * matrix.weights  # broadcasting over d
    distances = np.sqrt(weighted_sq.sum(axis=1))  # shape (n,)
    similarities = 1.0 / (1.0 + distances)

    aligned = aligned.assign(similarity=similarities)
    top = aligned.nlargest(k, "similarity")
    return top[["ref_date", "similarity", "forward_return_pct", "max_drawdown_pct"]].reset_index(
        drop=True
    )


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["ref_date", "similarity", "forward_return_pct", "max_drawdown_pct"]
    )
