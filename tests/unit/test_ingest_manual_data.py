"""Tester for `scripts/ingest_manual_data.py`.

Foreløpig dekker bare _CONAB_PRODUCT_MAP — fix § 7b 2026-04-28: CONAB-Excel
splitter algodao i "ALGODÃO EM PLUMA" + "ALGODÃO - CAROÇO". Vi mapper kun
pluma → algodao for å unngå PK-kollisjon på (report_date, commodity).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# scripts/ er ikke et package — last modulen direkte fra fil-stien.
_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ingest_manual_data.py"
_spec = importlib.util.spec_from_file_location("ingest_manual_data", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules["ingest_manual_data"] = _module
_spec.loader.exec_module(_module)

_CONAB_PRODUCT_MAP = _module._CONAB_PRODUCT_MAP


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
