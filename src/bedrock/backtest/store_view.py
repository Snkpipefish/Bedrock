# pyright: reportReturnType=false, reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false
# pandas-stubs false-positives på .loc/iloc-narrowing — se data/store.py for kontekst.

"""AsOfDateStore — wrapper rundt DataStore som klipper alle getters
til en gitt as-of-date.

Fase 11 session 63: brukes av `run_orchestrator_replay` for å simulere
"hva ville orchestrator generert på dato X?" uten å se data fra
fremtiden. Wrapper-mønsteret er valgt over å mutere DataStore selv —
slik at samme underliggende DB kan deles mellom flere
backtest-iterasjoner uten side-effekter.

Kontrakt: alle metoder bevarer signatur og returner-type fra `DataStore`.
Caller (Engine, drivere, find_analog_cases) skal ikke merke at den
jobber mot et clipped view.

**Outcomes-clipping** er strict: en outcome med `ref_date + horizon_days
> as_of_date` ekskluderes selv om raden eksisterer i underlying-tabellen
— fordi den representerer fremtidig informasjon (forward_return var
ikke kjent på `as_of_date`). Dette unngår look-ahead bias i K-NN.

**Begrensninger** (TODO for senere session):
- COT-rapporter publiseres med ~3 dagers etterslep (fredag rapport for
  forrige tirsdag). AsOfDateStore clipper på `report_date`, ikke
  publiseringsdato. For backtest-strict må vi senere flytte til
  publiseringsdato + 3d offset.
- Weather_monthly publiseres typisk månedslutt + ~2 uker. Samme
  publication-lag-problem.
- Vi clipper IKKE prices ved at vi rev-kalibrerer historiske bars —
  Yahoo kan ha endret bars fra 2010 (corporate actions etc.). For
  strict-backtest må vi snapshot prices på as_of_date.

Disse er flagget som potensielle avvik fra "perfekt" backtest-strict.
For dagens scope er look-ahead fra outcomes mest kritisk og er løst.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

import pandas as pd

if TYPE_CHECKING:
    from bedrock.data.store import DataStore


CotReport = Literal["disaggregated", "legacy"]


class AsOfDateStore:
    """Wrapper rundt DataStore som returnerer kun data ≤ `as_of_date`.

    Implementerer samme interface som `DataStore` for de getter-metodene
    som orchestrator + Engine + analog-K-NN bruker. Ikke-implementerte
    metoder kaster `AttributeError` — slik at vi får tydelig feilmelding
    hvis koden vokser ut over scope.

    `as_of_date` kan være `date`, `datetime`, eller `pd.Timestamp`.
    Internt normaliseres til naive `pd.Timestamp` (UTC midnatt) for
    sammenligning med DB-data som er naive datetimes.
    """

    def __init__(self, underlying: DataStore, as_of_date: date | datetime | pd.Timestamp) -> None:
        self._underlying = underlying
        self._as_of: pd.Timestamp = self._normalize_ts(as_of_date)

    @staticmethod
    def _normalize_ts(d: date | datetime | pd.Timestamp) -> pd.Timestamp:
        """Konverter til naive (tz-stripped) pd.Timestamp på UTC midnatt
        slik at sammenligning med DB-data er konsistent."""
        ts = pd.Timestamp(d)
        if ts.tz is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        # Hvis bare dato gitt, normaliser til midnatt
        if isinstance(d, date) and not isinstance(d, datetime):
            ts = ts.normalize()
        return ts

    @property
    def as_of_date(self) -> pd.Timestamp:
        """Eksponert for tester og introspeksjon."""
        return self._as_of

    # ------------------------------------------------------------------
    # Prices
    # ------------------------------------------------------------------

    def get_prices(
        self,
        instrument: str,
        tf: str = "D1",
        lookback: int | None = None,
    ) -> pd.Series:
        """Som DataStore.get_prices, men filtrert til ts ≤ as_of_date."""
        full = self._underlying.get_prices(instrument, tf=tf, lookback=None)
        clipped = self._clip_index(full)
        if clipped.empty:
            raise KeyError(
                f"No prices for instrument={instrument!r} tf={tf!r} as of {self._as_of.date()}"
            )
        if lookback is not None:
            clipped = clipped.tail(lookback)
        return clipped

    def get_prices_ohlc(
        self,
        instrument: str,
        tf: str = "D1",
        lookback: int | None = None,
    ) -> pd.DataFrame:
        """Som DataStore.get_prices_ohlc, men filtrert til ts ≤ as_of_date."""
        full = self._underlying.get_prices_ohlc(instrument, tf=tf, lookback=None)
        clipped = self._clip_index(full)
        if clipped.empty:
            raise KeyError(
                f"No prices for instrument={instrument!r} tf={tf!r} as of {self._as_of.date()}"
            )
        if lookback is not None:
            clipped = clipped.tail(lookback)
        return clipped

    def has_prices(self, instrument: str, tf: str) -> bool:
        try:
            return not self.get_prices(instrument, tf=tf).empty
        except KeyError:
            return False

    # ------------------------------------------------------------------
    # COT
    # ------------------------------------------------------------------

    def get_cot(
        self,
        contract: str,
        report: CotReport = "disaggregated",
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Som DataStore.get_cot, men filtrert til report_date ≤ as_of_date."""
        full = self._underlying.get_cot(contract, report=report, last_n=None)
        # report_date er pd.Timestamp etter parse i underlying
        clipped = full[full["report_date"] <= self._as_of].copy()
        if clipped.empty:
            raise KeyError(
                f"No COT for contract={contract!r} report={report!r} as of {self._as_of.date()}"
            )
        if last_n is not None:
            clipped = clipped.tail(last_n).reset_index(drop=True)
        return clipped

    # ------------------------------------------------------------------
    # Fundamentals
    # ------------------------------------------------------------------

    def get_fundamentals(
        self,
        series_id: str,
        last_n: int | None = None,
    ) -> pd.Series:
        """Som DataStore.get_fundamentals, men filtrert til date ≤ as_of_date."""
        full = self._underlying.get_fundamentals(series_id, last_n=None)
        clipped = self._clip_index(full)
        if clipped.empty:
            raise KeyError(
                f"No fundamentals for series_id={series_id!r} as of {self._as_of.date()}"
            )
        if last_n is not None:
            clipped = clipped.tail(last_n)
        return clipped

    # ------------------------------------------------------------------
    # Weather monthly
    # ------------------------------------------------------------------

    def get_weather_monthly(
        self,
        region: str,
        last_n: int | None = None,
    ) -> pd.DataFrame:
        """Som DataStore.get_weather_monthly, men filtrert til
        first-of-month ≤ as_of_date."""
        full = self._underlying.get_weather_monthly(region, last_n=None)
        # month-kolonnen er 'YYYY-MM'-streng; konverter til timestamp
        # for sammenligning. Antar måneden er kjent ved første dag.
        month_ts = pd.to_datetime(full["month"] + "-01")
        mask = month_ts <= self._as_of
        clipped = full[mask].reset_index(drop=True)
        if clipped.empty:
            raise KeyError(f"No monthly weather for region={region!r} as of {self._as_of.date()}")
        if last_n is not None:
            clipped = clipped.tail(last_n).reset_index(drop=True)
        return clipped

    # ------------------------------------------------------------------
    # Outcomes (look-ahead-strict)
    # ------------------------------------------------------------------

    def get_outcomes(
        self,
        instrument: str,
        ref_dates: Sequence[str | date | pd.Timestamp] | None = None,
        horizon_days: int | None = None,
    ) -> pd.DataFrame:
        """Som DataStore.get_outcomes, men strict-clipped:
        en outcome ekskluderes hvis `ref_date + horizon_days > as_of_date`
        — dvs. forward_return var ikke kjent på as_of_date.

        Gjør K-NN i orchestrator-replay leak-free: naboer er kun datoer
        der vi faktisk visste utfallet på as_of-tidspunktet.
        """
        full = self._underlying.get_outcomes(
            instrument, ref_dates=ref_dates, horizon_days=horizon_days
        )
        if full.empty:
            return full

        # Cutoff per rad: as_of_date - horizon_days. Hvis horizon_days er
        # gitt, samme cutoff for alle. Hvis None, bruk hver rads horizon.
        if horizon_days is not None:
            cutoff = self._as_of - pd.Timedelta(days=int(horizon_days))
            mask = full["ref_date"] <= cutoff
        else:
            cutoffs = self._as_of - pd.to_timedelta(full["horizon_days"], unit="D")
            mask = full["ref_date"] <= cutoffs
        return full[mask].reset_index(drop=True)

    # ------------------------------------------------------------------
    # Phase A-C tabeller (sub-fase 12.5+ sessions 105-115)
    #
    # Hver getter bevarer signatur og return-type fra DataStore. Clipping
    # gjøres på den naturlige dato-kolonnen (event_ts / report_date / date)
    # slik at orchestrator-replay ikke ser frem-i-tid-data.
    # ------------------------------------------------------------------

    def get_econ_events(
        self,
        countries: Sequence[str] | None = None,
        impact_levels: Sequence[str] | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
    ) -> pd.DataFrame:
        """Som DataStore.get_econ_events, men clipped på fetched_at.

        Bruker fetched_at fordi calendar-events er scheduled i fremtiden;
        spørsmålet er "hva visste vi på as_of_date?" — ikke "hvilke events
        hadde skjedd?". Hvis fetched_at-kolonnen mangler (gamle rader),
        faller vi tilbake til event_ts.
        """
        full = self._underlying.get_econ_events(
            countries=countries,
            impact_levels=impact_levels,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        if full.empty:
            return full
        as_of_utc = self._as_of.tz_localize("UTC") if self._as_of.tz is None else self._as_of
        if "fetched_at" in full.columns:
            mask = full["fetched_at"] <= as_of_utc
        else:
            mask = full["event_ts"] <= as_of_utc
        return full[mask].reset_index(drop=True)

    # COT-ICE — samme mønster som get_cot

    def get_cot_ice(self, contract: str, last_n: int | None = None) -> pd.DataFrame:
        """Som DataStore.get_cot_ice, men clipped på report_date ≤ as_of_date."""
        try:
            full = self._underlying.get_cot_ice(contract, last_n=None)
        except KeyError:
            raise
        clipped = full[full["report_date"] <= self._as_of].copy()
        if clipped.empty:
            raise KeyError(f"No ICE COT for contract={contract!r} as of {self._as_of.date()}")
        if last_n is not None:
            clipped = clipped.tail(last_n).reset_index(drop=True)
        return clipped

    def has_cot_ice(self, contract: str) -> bool:
        try:
            return not self.get_cot_ice(contract).empty
        except KeyError:
            return False

    # COT-Euronext

    def get_cot_euronext(self, contract: str, last_n: int | None = None) -> pd.DataFrame:
        """Som DataStore.get_cot_euronext, men clipped på report_date."""
        try:
            full = self._underlying.get_cot_euronext(contract, last_n=None)
        except KeyError:
            raise
        clipped = full[full["report_date"] <= self._as_of].copy()
        if clipped.empty:
            raise KeyError(f"No Euronext COT for contract={contract!r} as of {self._as_of.date()}")
        if last_n is not None:
            clipped = clipped.tail(last_n).reset_index(drop=True)
        return clipped

    def has_cot_euronext(self, contract: str) -> bool:
        try:
            return not self.get_cot_euronext(contract).empty
        except KeyError:
            return False

    # Conab

    def get_conab_estimates(self, commodity: str, last_n: int | None = None) -> pd.DataFrame:
        """Som DataStore.get_conab_estimates, men clipped på report_date."""
        try:
            full = self._underlying.get_conab_estimates(commodity, last_n=None)
        except KeyError:
            raise
        clipped = full[full["report_date"] <= self._as_of].copy()
        if clipped.empty:
            raise KeyError(f"No Conab data for commodity={commodity!r} as of {self._as_of.date()}")
        if last_n is not None:
            clipped = clipped.tail(last_n).reset_index(drop=True)
        return clipped

    def has_conab_estimates(self, commodity: str) -> bool:
        try:
            return not self.get_conab_estimates(commodity).empty
        except KeyError:
            return False

    # UNICA

    def get_unica_reports(self, last_n: int | None = None) -> pd.DataFrame:
        """Som DataStore.get_unica_reports, men clipped på report_date."""
        full = self._underlying.get_unica_reports(last_n=None)
        if full.empty:
            return full
        clipped = full[full["report_date"] <= self._as_of].reset_index(drop=True)
        if last_n is not None and not clipped.empty:
            clipped = clipped.tail(last_n).reset_index(drop=True)
        return clipped

    def has_unica_reports(self) -> bool:
        return not self.get_unica_reports().empty

    # EIA inventories

    def get_eia_inventory(self, series_id: str, last_n: int | None = None) -> pd.DataFrame:
        """Som DataStore.get_eia_inventory, men clipped på date."""
        try:
            full = self._underlying.get_eia_inventory(series_id, last_n=None)
        except KeyError:
            raise
        clipped = full[full["date"] <= self._as_of].copy()
        if clipped.empty:
            raise KeyError(
                f"No EIA inventory for series_id={series_id!r} as of {self._as_of.date()}"
            )
        if last_n is not None:
            clipped = clipped.tail(last_n).reset_index(drop=True)
        return clipped

    def has_eia_inventory(self, series_id: str) -> bool:
        try:
            return not self.get_eia_inventory(series_id).empty
        except KeyError:
            return False

    # COMEX

    def get_comex_inventory(self, metal: str, last_n: int | None = None) -> pd.DataFrame:
        """Som DataStore.get_comex_inventory, men clipped på date."""
        try:
            full = self._underlying.get_comex_inventory(metal, last_n=None)
        except KeyError:
            raise
        clipped = full[full["date"] <= self._as_of].copy()
        if clipped.empty:
            raise KeyError(f"No COMEX inventory for metal={metal!r} as of {self._as_of.date()}")
        if last_n is not None:
            clipped = clipped.tail(last_n).reset_index(drop=True)
        return clipped

    def has_comex_inventory(self, metal: str) -> bool:
        try:
            return not self.get_comex_inventory(metal).empty
        except KeyError:
            return False

    # Seismic

    def get_seismic_events(
        self,
        *,
        region: str | None = None,
        regions: Sequence[str] | None = None,
        from_ts: datetime | None = None,
        min_magnitude: float | None = None,
    ) -> pd.DataFrame:
        """Som DataStore.get_seismic_events, men clipped på event_ts."""
        full = self._underlying.get_seismic_events(
            region=region,
            regions=regions,
            from_ts=from_ts,
            min_magnitude=min_magnitude,
        )
        if full.empty:
            return full
        as_of_utc = self._as_of.tz_localize("UTC") if self._as_of.tz is None else self._as_of
        return full[full["event_ts"] <= as_of_utc].reset_index(drop=True)

    def has_seismic_events(self) -> bool:
        return self._underlying.has_seismic_events()

    # Shipping indices (Series med date-index)

    def get_shipping_index(self, index_code: str, last_n: int | None = None) -> pd.Series:
        """Som DataStore.get_shipping_index, men clipped på date-index."""
        try:
            full = self._underlying.get_shipping_index(index_code, last_n=None)
        except KeyError:
            raise
        clipped = self._clip_index(full)
        if clipped.empty:
            raise KeyError(f"No shipping index data for {index_code!r} as of {self._as_of.date()}")
        if last_n is not None:
            clipped = clipped.tail(last_n)
        return clipped

    def has_shipping_index(self, index_code: str | None = None) -> bool:
        if index_code is None:
            return self._underlying.has_shipping_index()
        try:
            return not self.get_shipping_index(index_code).empty
        except KeyError:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clip_index(self, df_or_series: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
        """Felles clip-by-index for pris-/fundamentals-data der vi har
        en datetime-indeks."""
        if df_or_series.empty:
            return df_or_series
        idx = df_or_series.index
        # Strip timezone hvis nødvendig for safe-sammenligning
        if isinstance(idx, pd.DatetimeIndex) and idx.tz is not None:
            idx_naive = idx.tz_convert("UTC").tz_localize(None)
        else:
            idx_naive = idx
        mask = idx_naive <= self._as_of
        return df_or_series[mask]
