"""Tester for `scripts/ingest_manual_data.py`.

Dekker:
- _CONAB_PRODUCT_MAP — fix § 7b 2026-04-28: CONAB-Excel splitter algodao i
  "ALGODÃO EM PLUMA" + "ALGODÃO - CAROÇO". Vi mapper kun pluma → algodao
  for å unngå PK-kollisjon på (report_date, commodity).
- ingest_forex_factory publication_lag_days — audit-runde 5 sub-fase 12.6
  fix-spec Steg 2: fetched_at = event_ts - publication_lag_days slik at
  AsOfDateStore-clipping gir look-ahead-fri backtest-semantikk.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd

# scripts/ er ikke et package — last modulen direkte fra fil-stien.
_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ingest_manual_data.py"
_spec = importlib.util.spec_from_file_location("ingest_manual_data", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules["ingest_manual_data"] = _module
_spec.loader.exec_module(_module)

_CONAB_PRODUCT_MAP = _module._CONAB_PRODUCT_MAP
ingest_forex_factory = _module.ingest_forex_factory


def test_conab_product_map_pluma_maps_to_algodao() -> None:
    """ALGODÃO EM PLUMA (lint, primær export-vare) skal mappe til algodao."""
    assert _CONAB_PRODUCT_MAP["ALGODÃO EM PLUMA"] == "algodao"
    assert _CONAB_PRODUCT_MAP["ALGODAO EM PLUMA"] == "algodao"


def test_conab_product_map_caroco_does_not_match() -> None:
    """ALGODÃO - CAROÇO (frø, biprodukt) skal IKKE mappe — ville kollidere
    med pluma på PK (report_date, commodity)."""
    assert "ALGODÃO - CAROÇO" not in _CONAB_PRODUCT_MAP
    assert "ALGODÃO - CAROÇO (1)" not in _CONAB_PRODUCT_MAP
    # Bekreft at oppslag returnerer None
    assert _CONAB_PRODUCT_MAP.get("ALGODÃO - CAROÇO (1)") is None


def test_conab_product_map_grains_intact() -> None:
    """Eksisterende grain-mappinger må fortsatt funke."""
    assert _CONAB_PRODUCT_MAP["MILHO TOTAL"] == "milho"
    assert _CONAB_PRODUCT_MAP["MILHO"] == "milho"
    assert _CONAB_PRODUCT_MAP["SOJA"] == "soja"
    assert _CONAB_PRODUCT_MAP["TRIGO"] == "trigo"


def test_conab_product_map_legacy_algodao_alias_kept() -> None:
    """Bare 'ALGODÃO' (uten suffix) beholdes som alias for PDF-fetcher
    som ikke har splittet pluma/caroço."""
    assert _CONAB_PRODUCT_MAP["ALGODÃO"] == "algodao"
    assert _CONAB_PRODUCT_MAP["ALGODAO"] == "algodao"


# ---------------------------------------------------------------------------
# ingest_forex_factory — publication_lag_days (audit 12.6 Sjekk 9.5 Steg 2)
# ---------------------------------------------------------------------------


class _CapturingStore:
    """Stub som fanger DataFrame som sendes til ``append_econ_events``."""

    def __init__(self) -> None:
        self.captured: pd.DataFrame | None = None

    def append_econ_events(self, df: pd.DataFrame) -> int:
        self.captured = df.copy()
        return len(df)


def _write_minimal_ff_csv(path: Path) -> None:
    """Skriv en minimal Forex Factory CSV med 2 High og 1 Low (skal filtreres)."""
    rows = pd.DataFrame(
        [
            {
                "DateTime": "2010-02-12 13:30:00",
                "Currency": "USD",
                "Event": "NFP Release",
                "Impact": "High Impact Expected",
                "Forecast": "200K",
                "Previous": "150K",
            },
            {
                "DateTime": "2010-02-15 09:00:00",
                "Currency": "EUR",
                "Event": "ECB Speech",
                "Impact": "Medium Impact Expected",
                "Forecast": "",
                "Previous": "",
            },
            {
                "DateTime": "2010-02-16 12:00:00",
                "Currency": "GBP",
                "Event": "Filler Low",
                "Impact": "Low Impact Expected",
                "Forecast": "",
                "Previous": "",
            },
        ]
    )
    rows.to_csv(path, index=False)


def test_forex_factory_default_lag_is_seven_days(tmp_path: Path) -> None:
    """Default publication_lag_days=7 → fetched_at = event_ts - 7d for alle rader."""
    csv_path = tmp_path / "ff_mini.csv"
    _write_minimal_ff_csv(csv_path)

    store = _CapturingStore()
    n = ingest_forex_factory(csv_path, store)

    assert n == 2  # Low filtreres ut
    df = store.captured
    assert df is not None
    # Alle ingestede rader: fetched_at < event_ts (7-dagers default-lag)
    assert (df["fetched_at"] < df["event_ts"]).all()
    deltas = (df["event_ts"] - df["fetched_at"]).unique()
    assert len(deltas) == 1
    assert deltas[0] == pd.Timedelta(days=7)


def test_forex_factory_explicit_lag_days_applied(tmp_path: Path) -> None:
    """Eksplisitt publication_lag_days=14 → fetched_at = event_ts - 14d."""
    csv_path = tmp_path / "ff_mini.csv"
    _write_minimal_ff_csv(csv_path)

    store = _CapturingStore()
    ingest_forex_factory(csv_path, store, publication_lag_days=14)

    df = store.captured
    assert df is not None
    assert (df["fetched_at"] < df["event_ts"]).all()
    deltas = (df["event_ts"] - df["fetched_at"]).unique()
    assert len(deltas) == 1
    assert deltas[0] == pd.Timedelta(days=14)


def test_forex_factory_zero_lag_keeps_event_ts(tmp_path: Path) -> None:
    """publication_lag_days=0 → fetched_at == event_ts (gammel buggy oppførsel,
    eksponert som eksplisitt valg slik at re-import med samme semantikk er
    mulig hvis man trenger det)."""
    csv_path = tmp_path / "ff_mini.csv"
    _write_minimal_ff_csv(csv_path)

    store = _CapturingStore()
    ingest_forex_factory(csv_path, store, publication_lag_days=0)

    df = store.captured
    assert df is not None
    assert (df["fetched_at"] == df["event_ts"]).all()
