"""Instrument-config YAML-lasting.

Per PLAN § 4.2 (Gold) og § 4.3 (Corn): hvert instrument har sin egen YAML-
fil i `config/instruments/*.yaml` som kombinerer:

- **Metadata**: id, asset_class, ticker-er, CFTC-kontrakt, vær-region
  og -koordinater, FRED-serie(r) — alt som trengs av fetch-laget +
  setup-generator + UI for å identifisere og operere på instrumentet
- **Rules**: aggregation + horizons + families + grade_thresholds,
  direkte inn i `FinancialRules` / `AgriRules` fra `bedrock.engine.engine`

YAML-strukturen speiler PLAN. Top-level-nøkler deles i to grupper:

```yaml
# ---- metadata ----
instrument:
  id: Gold
  asset_class: metals
  ticker: XAUUSD
  cfd_ticker: Gold
  cot_contract: "GOLD - COMMODITY EXCHANGE INC."

# ---- rules (går direkte til Engine) ----
aggregation: weighted_horizon
horizons: { ... }
families: { ... }
grade_thresholds: { ... }
```

`inherits: family_financial` (PLAN § 4.2) er utsatt til senere session —
session 21 kjører flat YAML uten inheritance. Gates er også utsatt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from bedrock.engine.engine import AgriRules, FinancialRules


class InstrumentMetadata(BaseModel):
    """Metadata som fetch-lag, setup-generator og UI trenger for å
    identifisere et instrument.

    Alle ikke-påkrevde felt er `None` hvis instrumentet ikke bruker
    den kilden (f.eks. FX har ingen `cot_contract` i agri-forstand,
    metals har ikke `weather_region`).
    """

    id: str  # Bedrocks interne navn, f.eks. "Gold", "EURUSD", "Corn"
    asset_class: str  # "metals", "fx", "energy", "indices", "crypto", "grains", "softs"
    ticker: str  # primær pris-ticker (f.eks. "XAUUSD", "ZC")
    cfd_ticker: str | None = None  # broker-spesifikk (cTrader-routing)

    # Fetch-relaterte optional
    stooq_ticker: str | None = None  # avvik fra `ticker` hvis Stooq har annet navn
    cot_contract: str | None = None  # CFTC `market_and_exchange_names` eksakt
    cot_report: str | None = None  # "disaggregated" eller "legacy"
    weather_region: str | None = None  # Bedrock-intern tag for DataStore
    weather_lat: float | None = None
    weather_lon: float | None = None
    fred_series_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class InstrumentConfig(BaseModel):
    """Full konfigurasjon for ett instrument: metadata + rules.

    `rules` er enten `FinancialRules` eller `AgriRules` — diskriminert
    via `aggregation`-feltet. Engine tar `rules` direkte.
    """

    instrument: InstrumentMetadata
    rules: FinancialRules | AgriRules

    model_config = ConfigDict(extra="forbid")


class InstrumentConfigError(ValueError):
    """YAML parsed men struktur er ugyldig for instrument-config."""


# ---------------------------------------------------------------------------
# YAML-lasting
# ---------------------------------------------------------------------------


def load_instrument_config(path: Path | str) -> InstrumentConfig:
    """Les og valider én instrument-YAML.

    Reiser `InstrumentConfigError` ved manglende `instrument`-blokk eller
    ukjent aggregation. Pydantic-valideringsfeil propageres (caller ser
    hva som er galt).
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Instrument config not found: {target}")

    with target.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise InstrumentConfigError(
            f"{target}: expected YAML mapping at root, got {type(data).__name__}"
        )

    return _parse_instrument_dict(data, source=str(target))


def load_all_instruments(directory: Path | str) -> dict[str, InstrumentConfig]:
    """Les alle `*.yaml` i katalog og returner som `{instrument.id: config}`.

    Duplikate IDer kaster `InstrumentConfigError`. Non-YAML-filer og
    underkataloger ignoreres. Tom katalog returnerer tom dict.
    """
    target = Path(directory)
    if not target.exists():
        raise FileNotFoundError(f"Instruments directory not found: {target}")

    result: dict[str, InstrumentConfig] = {}
    for yaml_path in sorted(target.glob("*.yaml")):
        cfg = load_instrument_config(yaml_path)
        inst_id = cfg.instrument.id
        if inst_id in result:
            raise InstrumentConfigError(
                f"Duplicate instrument id {inst_id!r} in "
                f"{yaml_path.name} (also in earlier file)"
            )
        result[inst_id] = cfg

    return result


# ---------------------------------------------------------------------------
# Private: YAML → Pydantic
# ---------------------------------------------------------------------------

# Top-level YAML-nøkler som hører til `rules`-delen (ikke metadata).
_RULES_KEYS: frozenset[str] = frozenset(
    {
        "aggregation",
        "horizons",
        "families",
        "grade_thresholds",
        "max_score",
        "min_score_publish",
    }
)

# Nøkler som er bevisst utsatt til senere session — vi ignorerer dem nå
# uten error slik at YAML-er skrevet for fremtiden ikke bryter i dag.
_DEFERRED_KEYS: frozenset[str] = frozenset(
    {
        "inherits",  # Fase 5 senere: familie-defaults inheritance
        "gates",  # PLAN § 4.2 cap_grade-regler
        "usda_blackout",  # agri-spesifikk kalender-gate
    }
)


def _parse_instrument_dict(data: dict[str, Any], source: str) -> InstrumentConfig:
    """Konverter rå YAML-dict til `InstrumentConfig`."""
    if "instrument" not in data:
        raise InstrumentConfigError(
            f"{source}: missing required 'instrument' block"
        )

    metadata = InstrumentMetadata.model_validate(data["instrument"])

    rules_data: dict[str, Any] = {}
    unknown_keys: list[str] = []
    for key, value in data.items():
        if key == "instrument":
            continue
        if key in _DEFERRED_KEYS:
            continue  # stille skip — kommer i senere session
        if key in _RULES_KEYS:
            rules_data[key] = value
        else:
            unknown_keys.append(key)

    if unknown_keys:
        raise InstrumentConfigError(
            f"{source}: unknown top-level keys: {sorted(unknown_keys)}. "
            f"Known: instrument + {sorted(_RULES_KEYS)}. "
            f"Deferred (ignored silently): {sorted(_DEFERRED_KEYS)}"
        )

    aggregation = rules_data.get("aggregation")
    if aggregation == "weighted_horizon":
        rules = FinancialRules.model_validate(rules_data)
    elif aggregation == "additive_sum":
        rules = AgriRules.model_validate(rules_data)
    else:
        raise InstrumentConfigError(
            f"{source}: unknown or missing 'aggregation'. "
            f"Expected 'weighted_horizon' or 'additive_sum', got {aggregation!r}"
        )

    return InstrumentConfig(instrument=metadata, rules=rules)


__all__ = [
    "InstrumentMetadata",
    "InstrumentConfig",
    "InstrumentConfigError",
    "load_instrument_config",
    "load_all_instruments",
]
