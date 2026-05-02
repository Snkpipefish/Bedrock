"""Sub-fase 12.10 Bunke 7 — GIE-utvidelse + COT-disaggregated.

Per § 22.2 #23-#26.

#23 AGSI per-land (5 drivere):
- agsi_germany_pct (DE), agsi_netherlands_pct (NL), agsi_italy_pct (IT) —
  thin wrappers rundt eksisterende agsi_storage_pct.
- agsi_withdrawal_rate, agsi_injection_rate — nye drivere som leser
  withdrawal_twh / injection_twh-kolonnene direkte.

#24 ALSI: levert i sub-fase 12.10 follow-up Spor C (session 136):
- alsi_eu_pct: LNG-terminal full_pct (parallel til agsi_storage_pct).
- alsi_storage_change: WoW %-endring i inventory.

#25 IIP REMIT: levert i sub-fase 12.10 follow-up Spor C (session 136):
- iip_supply_unavailability: aggregert capacity unavailable nå/nylig.

#26 COT-disaggregated utvidelser (4 av 4 etter Spor F5 2026-05-02):
- cot_oi_change: open_interest WoW-change z-score
- cot_commercial_extreme: Commercial-positioning ekstrem (kontrært)
- cot_concentration_top4: Spor F5 — top-4-traders net concentration (% av OI)
- cot_swap_dealer_skew: Spor F5 — Swap Dealer net skew vs OI (Disaggregated
  har Swap Dealer-kolonner; spec mente opprinnelig TFF, korrigert per
  CFTC-domenekunnskap — TFF har Dealer/Asset Mgr/Lev Funds men ikke Swap)
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from bedrock.engine.drivers import get, register
from bedrock.engine.drivers.macro_bunke3 import _compute_z, _step

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# #23 AGSI per-land (thin wrappers)
# ---------------------------------------------------------------------------


def _agsi_country_wrapper(store: Any, instrument: str, params: dict, *, country: str) -> float:
    base_fn = get("agsi_storage_pct")
    sub_params = dict(params)
    sub_params["country"] = country
    return base_fn(store, instrument, sub_params)


@register("agsi_germany_pct")
def agsi_germany_pct(store: Any, instrument: str, params: dict) -> float:
    """AGSI Germany gas-storage fyllingsgrad."""
    return _agsi_country_wrapper(store, instrument, params, country="de")


@register("agsi_netherlands_pct")
def agsi_netherlands_pct(store: Any, instrument: str, params: dict) -> float:
    """AGSI Netherlands gas-storage fyllingsgrad."""
    return _agsi_country_wrapper(store, instrument, params, country="nl")


@register("agsi_italy_pct")
def agsi_italy_pct(store: Any, instrument: str, params: dict) -> float:
    """AGSI Italy gas-storage fyllingsgrad."""
    return _agsi_country_wrapper(store, instrument, params, country="it")


# ---------------------------------------------------------------------------
# AGSI withdrawal/injection rates
# ---------------------------------------------------------------------------


def _agsi_rate_driver(store: Any, instrument: str, params: dict, *, column: str) -> float:
    """Felles helper for withdrawal/injection-rate-drivere."""
    _ = params.get("_horizon")
    country = str(params.get("country", "eu")).lower()
    bull_when = str(params.get("bull_when", "high")).lower()
    lookback_days = int(params.get("lookback_days", 252))
    min_samples = int(params.get("min_samples", 30))

    try:
        df = store.get_agsi_storage(country)
    except Exception:
        return 0.0

    if df is None or df.empty or column not in df.columns:
        return 0.0

    series = pd.Series(
        df[column].astype("float64").values,
        index=pd.to_datetime(df["gas_day_start"]),
    ).dropna()

    if len(series) < min_samples:
        return 0.5

    z = _compute_z(series, lookback=lookback_days)
    if z is None:
        return 0.5

    z_oriented = z if bull_when == "high" else -z
    if z_oriented >= 2.0:
        return 1.0
    if z_oriented >= 1.0:
        return 0.75
    if z_oriented >= 0.5:
        return 0.6
    if z_oriented >= 0.0:
        return 0.5
    if z_oriented >= -0.5:
        return 0.3
    return 0.0


@register("agsi_withdrawal_rate")
def agsi_withdrawal_rate(store: Any, instrument: str, params: dict) -> float:
    """AGSI withdrawal-rate (TWh/dag) z-score. Default bull_when='high' (høyt
    uttak = stress på supply = bull NG). Override via YAML."""
    return _agsi_rate_driver(store, instrument, params, column="withdrawal_twh")


@register("agsi_injection_rate")
def agsi_injection_rate(store: Any, instrument: str, params: dict) -> float:
    """AGSI injection-rate (TWh/dag) z-score. Default bull_when='low' (lav
    injeksjon = trang supply = bull NG)."""
    # Override default bull_when til 'low' for injection
    p = dict(params)
    p.setdefault("bull_when", "low")
    return _agsi_rate_driver(store, instrument, p, column="injection_twh")


# ---------------------------------------------------------------------------
# #24 ALSI EU LNG-terminal (sub-fase 12.10 follow-up Spor C, session 136)
# ---------------------------------------------------------------------------


_DEFAULT_ALSI_PCT_THRESHOLDS_LOW: tuple[tuple[float, float], ...] = (
    # bull_when="low": lav LNG-fyllingsgrad = bull NG (mindre import-buffer).
    (15.0, 1.0),  # < 15% = sterk bull (LNG-stress)
    (30.0, 0.75),  # 15-30% = bull
    (55.0, 0.5),  # 30-55% = nøytral
    (75.0, 0.25),  # 55-75% = bear
    (100.0, 0.1),  # >75% = sterk bear (LNG-overflow)
)


@register("alsi_eu_pct")
def alsi_eu_pct(store: Any, instrument: str, params: dict) -> float:
    """ALSI EU LNG-terminal fyllingsgrad mappet til 0..1.

    Søsken til ``agsi_storage_pct``, men leser ALSI (LNG-terminaler) i stedet
    for AGSI (underjordisk gas-storage). LNG-buffer er 2. linjeforsvar mot
    EU gas-supply-shock — lav LNG-fyllingsgrad signaliserer at terminalene
    sender ut til grid raskere enn de fylles, ofte indikator på trang
    supply/høyt forbruk → bull NG-pris.

    Default (mode=None): step-mapping på rå ``full_pct`` (0..100) fra siste
    ALSI-observasjon. R4-modes: pct_12m/pct_36m via rolling-percentile,
    delta_5d_z/delta_20d_z via daglig z-score, extreme_flag_*.

    Frekvens: ALSI publiserer daglig D+1 (samme kadens som AGSI).

    Tolkning:
        bull_when="low" (default): lav fyllingsgrad = bull NG-pris.
        bull_when="high": invertert.

    Params:
        country: ALSI-country-key. Default ``"eu"``. Per-land tilgjengelig:
            "de", "nl", "fr", "it", "es" etc.
        bull_when: ``"low"`` (default) eller ``"high"``.
        thresholds: optional override.
        mode: feature-velger per ADR-010 (forbeholdt — denne v1-iterasjonen
            implementerer kun default-trapp; pct_*/delta_* TBD).
        _horizon: engine-injisert per ADR-010. Lest, ikke brukt.

    Defensive 0.0 ved manglende data eller utilstrekkelig historikk.
    """
    _ = params.get("_horizon")
    country = str(params.get("country", "eu")).lower()
    bull_when = str(params.get("bull_when", "low")).lower()

    try:
        df = store.get_alsi_storage(country)
    except KeyError:
        _log.debug("alsi_eu_pct.no_data", instrument=instrument, country=country)
        return 0.0
    except Exception as exc:
        _log.warning("alsi_eu_pct.fetch_failed", instrument=instrument, error=str(exc))
        return 0.0

    if df.empty or "full_pct" not in df.columns:
        return 0.0

    series = pd.Series(
        df["full_pct"].astype("float64").values,
        index=pd.to_datetime(df["gas_day_start"]),
    ).dropna()

    if series.empty:
        return 0.0

    current = float(series.iloc[-1])

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_ALSI_PCT_THRESHOLDS_LOW
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    score = 0.0
    for threshold, s in sorted(steps, key=lambda t: t[0]):
        if current <= threshold:
            score = float(s)
            break

    if bull_when == "high":
        return round(1.0 - score, 4)
    return round(score, 4)


_DEFAULT_ALSI_CHANGE_THRESHOLDS_LOW: tuple[tuple[float, float], ...] = (
    # bull_when="low": stort fall i inventory = bull (rask drawdown signaliserer
    # supply-shortage/høyt forbruk).
    (-10.0, 1.0),  # ≤ -10% WoW = sterk bull (kraftig drawdown)
    (-5.0, 0.75),
    (0.0, 0.5),  # nøytral rundt flat
    (5.0, 0.25),
    (float("inf"), 0.0),  # > +5% WoW = bear (rask refill)
)


@register("alsi_storage_change")
def alsi_storage_change(store: Any, instrument: str, params: dict) -> float:
    """ALSI inventory %-endring over WoW (eller `lookback_days` window).

    Default: 5-dagers %-endring i ``inventory_twh`` (LNG-volum), step-
    mappet til 0..1. Stor drawdown = supply consumed = bull NG.

    Params:
        country: ALSI-country-key. Default ``"eu"``.
        lookback_days: dager tilbake for endrings-beregning. Default 5.
        bull_when: ``"low"`` (default — drawdown = bull) eller ``"high"``.
        thresholds: optional override.
    """
    _ = params.get("_horizon")
    country = str(params.get("country", "eu")).lower()
    lookback_days = int(params.get("lookback_days", 5))
    bull_when = str(params.get("bull_when", "low")).lower()
    min_samples = int(params.get("min_samples", 10))

    try:
        df = store.get_alsi_storage(country)
    except Exception:
        return 0.0

    if df.empty or "inventory_twh" not in df.columns:
        return 0.0

    series = pd.Series(
        df["inventory_twh"].astype("float64").values,
        index=pd.to_datetime(df["gas_day_start"]),
    ).dropna()

    if len(series) < min_samples:
        return 0.5

    if len(series) <= lookback_days:
        return 0.5

    current = float(series.iloc[-1])
    past = float(series.iloc[-(lookback_days + 1)])
    if past == 0:
        return 0.5
    pct_change = (current - past) / past * 100.0

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_ALSI_CHANGE_THRESHOLDS_LOW
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    score = _step(pct_change, steps)

    if bull_when == "high":
        return round(1.0 - score, 4)
    return round(score, 4)


# ---------------------------------------------------------------------------
# #25 IIP REMIT supply-unavailability (sub-fase 12.10 follow-up Spor C, s136)
# ---------------------------------------------------------------------------


_DEFAULT_IIP_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    # bull_when="high": høy aggregert unavailable_capacity = supply trang = bull.
    # Empirisk EU baseline: ~500-2000 GWh/d kontinuerlig planned-maintenance.
    (500.0, 0.0),  # ≤ 500 GWh/d = lav stress, bear
    (1000.0, 0.25),
    (2000.0, 0.5),  # 1000-2000 GWh/d = moderat
    (5000.0, 0.75),
    (float("inf"), 1.0),  # > 5000 GWh/d = stor disruption, sterk bull
)


@register("iip_supply_unavailability")
def iip_supply_unavailability(store: Any, instrument: str, params: dict) -> float:
    """IIP REMIT aggregert supply-unavailability mappet til 0..1.

    Sum av ``unavailable_capacity_gwhd`` for events som er aktive nå
    (event_from_ts ≤ as_of ≤ event_to_ts) eller publisert i siste
    ``lookback_days``-vindu — avhengig av ``mode``.

    Tolkning: høy aggregert unavailability = supply trang = bull NG/Brent.
    Default bull_when='high'.

    Modes:
        ``"active"`` (default): events aktive ved as_of (sist-rad-dato i DB).
        ``"recent"``: events publisert i siste ``lookback_days``.

    Params:
        balancing_zone_prefix: optional zone-filter (f.eks. "21YNL" for NL TTF).
        mode: ``"active"`` (default) eller ``"recent"``.
        lookback_days: kun for ``mode="recent"`` (default 30).
        bull_when: ``"high"`` (default) eller ``"low"``.
        thresholds: optional override (sortert ASC på terskel i GWh/d).
        unavailability_type: optional filter ("Planned"/"Unplanned"/None).
        min_events: minimum events for å returnere score (default 0; ellers 0.5).
        _horizon: engine-injisert. Lest, ikke brukt.

    Defensive 0.5 (nøytral) ved tom data — IIP-stress-fravær er ikke et
    bear-signal, bare informasjons-fravær.
    """
    _ = params.get("_horizon")
    bz_prefix = params.get("balancing_zone_prefix")
    mode = str(params.get("mode", "active")).lower()
    lookback_days = int(params.get("lookback_days", 30))
    bull_when = str(params.get("bull_when", "high")).lower()
    unavailability_type = params.get("unavailability_type")
    min_events = int(params.get("min_events", 0))

    try:
        df = store.get_iip_remit(balancing_zone_prefix=bz_prefix)
    except Exception:
        return 0.5

    if df is None or df.empty:
        return 0.5

    pub_ts = pd.to_datetime(df["published_ts"], errors="coerce")
    df = df[pub_ts.notna()].copy()
    if df.empty:
        return 0.5

    pub_ts = pd.to_datetime(df["published_ts"])
    as_of = pub_ts.max()

    if unavailability_type is not None:
        df = df[df["unavailability_type"].astype(str) == str(unavailability_type)]
        if df.empty:
            return 0.5

    if mode == "active":
        from_ts = pd.to_datetime(df["event_from_ts"], errors="coerce")
        to_ts = pd.to_datetime(df["event_to_ts"], errors="coerce")
        active_mask = (from_ts <= as_of) & (to_ts >= as_of)
        active = df[active_mask]
    elif mode == "recent":
        cutoff = as_of - pd.Timedelta(days=lookback_days)
        active = df[pd.to_datetime(df["published_ts"]) >= cutoff]
    else:
        _log.warning(
            "iip_supply_unavailability.unknown_mode_falling_back_to_active",
            instrument=instrument,
            mode=mode,
        )
        from_ts = pd.to_datetime(df["event_from_ts"], errors="coerce")
        to_ts = pd.to_datetime(df["event_to_ts"], errors="coerce")
        active_mask = (from_ts <= as_of) & (to_ts >= as_of)
        active = df[active_mask]

    if len(active) <= min_events:
        return 0.5

    cap_series = active["unavailable_capacity_gwhd"].astype("float64").dropna()
    total = float(cap_series.sum()) if not cap_series.empty else 0.0

    user_thresholds = params.get("thresholds")
    if user_thresholds is None:
        steps = _DEFAULT_IIP_THRESHOLDS_BULL_HIGH
    else:
        steps = tuple((float(t), float(s)) for t, s in user_thresholds)

    score = _step(total, steps)

    if bull_when == "low":
        return round(1.0 - score, 4)
    return round(score, 4)


# ---------------------------------------------------------------------------
# #26 COT utvidelser (4 av 4 etter Spor F5 — fra 2 til 4 ved 2026-05-02)
# ---------------------------------------------------------------------------


_OI_CHANGE_THRESHOLDS_BULL_HIGH: tuple[tuple[float, float], ...] = (
    (-2.0, 0.0),  # store OI-fall = bear/risk-off
    (-1.0, 0.25),
    (0.0, 0.5),
    (1.0, 0.75),
    (float("inf"), 1.0),
)


@register("cot_oi_change")
def cot_oi_change(store: Any, instrument: str, params: dict) -> float:
    """COT open_interest WoW-change z-score.

    Tolkning: økning i OI = nye penger inn = trend-følger-momentum
    (bull-of-trend); fall i OI = posisjon-lukking = mean-revert-signal.
    Default bull_when='high'.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    contract = str(params.get("contract", ""))
    report = str(params.get("report", "disaggregated"))
    lookback_weeks = int(params.get("lookback_weeks", 52))
    min_samples = int(params.get("min_samples", 30))

    if not contract:
        return 0.0

    try:
        df = store.get_cot(contract, report=report)
    except Exception:
        return 0.0

    if df is None or df.empty or "open_interest" not in df.columns:
        return 0.0

    series = pd.Series(
        df["open_interest"].astype("float64").values,
        index=pd.to_datetime(df["report_date"]),
    ).dropna()

    if len(series) < min_samples:
        return 0.5

    # WoW = pct change: (current - prev) / prev
    if len(series) < 2:
        return 0.5
    chg_series = series.pct_change().dropna() * 100.0
    if len(chg_series) < min_samples:
        return 0.5

    z = _compute_z(chg_series, lookback=lookback_weeks)
    if z is None:
        return 0.5

    z_oriented = z if bull_when == "high" else -z
    score = _step(z_oriented, _OI_CHANGE_THRESHOLDS_BULL_HIGH)
    return score


@register("cot_commercial_extreme")
def cot_commercial_extreme(store: Any, instrument: str, params: dict) -> float:
    """Commercial-positioning ekstrem-flag (kontrært-signal).

    Commercials er typisk hedgers (produsenter/forbrukere) som tar motsatt
    posisjon av spekulanter. Ekstrem long = bull-of-prising; ekstrem short
    = bear-of-prising. Default bull_when='high' = commercial long ekstrem
    er bullish.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    contract = str(params.get("contract", ""))
    report = str(params.get("report", "disaggregated"))
    lookback_weeks = int(params.get("lookback_weeks", 156))  # 3 år
    min_samples = int(params.get("min_samples", 52))

    if not contract:
        return 0.0

    try:
        df = store.get_cot(contract, report=report)
    except Exception:
        return 0.0

    if df is None or df.empty or "comm_long" not in df.columns:
        return 0.0

    long_s = df["comm_long"].astype("float64")
    short_s = df["comm_short"].astype("float64")
    oi = df["open_interest"].astype("float64").replace(0, float("nan"))
    net_pct = ((long_s - short_s) / oi).dropna() * 100.0

    if len(net_pct) < min_samples:
        return 0.5

    # Rolling-percentile av siste obs
    window = net_pct.tail(lookback_weeks + 1).dropna()
    if len(window) < 10:
        return 0.5
    current = float(window.iloc[-1])
    history = window.iloc[:-1]
    rank = float((history < current).sum()) / float(len(history))

    # Map rank til kontrært score: høy commercial-long = bullish (bull_when='high')
    score = rank if bull_when == "high" else 1.0 - rank
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Spor F5 (2026-05-02): cot_concentration_top4 + cot_swap_dealer_skew
# ---------------------------------------------------------------------------


@register("cot_concentration_top4")
def cot_concentration_top4(store: Any, instrument: str, params: dict) -> float:
    """Konsentrasjon-av-største-4-traders i COT-disaggregated (Spor F5).

    Reads `conc_net_top4` (% av OI holdt netto av top-4-largest-traders, long
    side) fra cot_disaggregated. Høy konsentrasjon = tynn likviditet =
    volatilitets-risiko = risk-off-bias. Default ``bull_when='low'`` antar
    sunn breddebalanse er bullish; flip til 'high' for instrumenter hvor
    institusjonell konsentrasjon korrelerer positivt med pris-momentum.

    Returnerer 0..1 via percentile-mapping mot `lookback_weeks` historikk
    (default 156 = 3 år). Returns 0.0 hvis kontrakt mangler i DB; 0.5 hvis
    historikk for kort eller `conc_net_top4`-kolonnen er NULL for alle
    nylige rader (typisk pre-Spor-F5-backfill-tilstand).

    Konfigurerbar via ``params["top"] = 8`` for å lese ``conc_net_top8``
    i stedet (top-8-konsentrasjonen er ofte mer stabil).
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "low")).lower()
    contract = str(params.get("contract", ""))
    report = str(params.get("report", "disaggregated"))
    lookback_weeks = int(params.get("lookback_weeks", 156))
    min_samples = int(params.get("min_samples", 26))
    top = int(params.get("top", 4))
    col = "conc_net_top4" if top == 4 else "conc_net_top8"

    if not contract:
        return 0.0

    try:
        df = store.get_cot(contract, report=report)
    except Exception:
        return 0.0

    if df is None or df.empty or col not in df.columns:
        return 0.0

    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(s) < min_samples:
        return 0.5

    window = s.tail(lookback_weeks + 1).dropna()
    if len(window) < 10:
        return 0.5
    current = float(window.iloc[-1])
    history = window.iloc[:-1]
    rank = float((history < current).sum()) / float(len(history))

    score = rank if bull_when == "high" else 1.0 - rank
    return max(0.0, min(1.0, score))


@register("cot_swap_dealer_skew")
def cot_swap_dealer_skew(store: Any, instrument: str, params: dict) -> float:
    """Swap Dealer net-positioning-skew vs OI (Spor F5).

    Reads `swap_long` + `swap_short` fra cot_disaggregated. Beregner
    `(swap_long - swap_short) / open_interest * 100` og percentile-mapper
    mot `lookback_weeks` historikk. Default ``bull_when='high'``: stort
    swap-net-long = institusjonelle dealere posisjonerer for høyere priser
    = bullish (også typisk markeds-leder for sentiment).

    Som med kommersielle: tolkning kan flippes ('low') for kontrarian-
    instrumenter hvor dealer-positioning er hedge-driven motstrøms.

    Returnerer 0..1 via percentile-rank (samme pattern som cot_commercial_
    extreme). Returns 0.0 hvis kontrakt/kolonne mangler; 0.5 hvis historikk
    for kort.
    """
    _ = params.get("_horizon")
    bull_when = str(params.get("bull_when", "high")).lower()
    contract = str(params.get("contract", ""))
    report = str(params.get("report", "disaggregated"))
    lookback_weeks = int(params.get("lookback_weeks", 156))
    min_samples = int(params.get("min_samples", 26))

    if not contract:
        return 0.0

    try:
        df = store.get_cot(contract, report=report)
    except Exception:
        return 0.0

    if df is None or df.empty or "swap_long" not in df.columns or "swap_short" not in df.columns:
        return 0.0

    long_s = pd.to_numeric(df["swap_long"], errors="coerce")
    short_s = pd.to_numeric(df["swap_short"], errors="coerce")
    oi = pd.to_numeric(df["open_interest"], errors="coerce").replace(0, float("nan"))
    skew = ((long_s - short_s) / oi).dropna() * 100.0

    if len(skew) < min_samples:
        return 0.5

    window = skew.tail(lookback_weeks + 1).dropna()
    if len(window) < 10:
        return 0.5
    current = float(window.iloc[-1])
    history = window.iloc[:-1]
    rank = float((history < current).sum()) / float(len(history))

    score = rank if bull_when == "high" else 1.0 - rank
    return max(0.0, min(1.0, score))


__all__ = [
    "agsi_germany_pct",
    "agsi_injection_rate",
    "agsi_italy_pct",
    "agsi_netherlands_pct",
    "agsi_withdrawal_rate",
    "alsi_eu_pct",
    "alsi_storage_change",
    "cot_commercial_extreme",
    "cot_concentration_top4",
    "cot_oi_change",
    "cot_swap_dealer_skew",
    "iip_supply_unavailability",
]
