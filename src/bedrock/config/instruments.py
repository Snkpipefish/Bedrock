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

`inherits: family_financial` (PLAN § 4.2) resolves rekursivt fra
`config/defaults/` (session 23). Shallow merge på top-level keys —
barnets felter vinner. `gates` og `usda_blackout` er fortsatt stille-
skippet til egne sessions implementerer scoring/kalender-støtte.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from bedrock.engine.engine import AgriRules, FinancialRules

DEFAULT_DEFAULTS_DIR = Path("config/defaults")


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
    yahoo_ticker: str | None = None  # Yahoo Finance-ticker (f.eks. "GC=F" for Gold)
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


def load_instrument_config(
    path: Path | str,
    defaults_dir: Path | str | None = None,
) -> InstrumentConfig:
    """Les og valider én instrument-YAML.

    `inherits: <name>` resolves rekursivt mot `defaults_dir` (default:
    `config/defaults/`). Shallow merge på top-level keys — barnets felter
    vinner. Se `_resolve_inherits` for full semantikk.

    Reiser `InstrumentConfigError` ved manglende `instrument`-blokk,
    ukjent aggregation, manglende parent, eller circular inheritance.
    Pydantic-valideringsfeil propageres (caller ser hva som er galt).
    """
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Instrument config not found: {target}")

    resolved_defaults = Path(defaults_dir) if defaults_dir is not None else DEFAULT_DEFAULTS_DIR

    with target.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise InstrumentConfigError(
            f"{target}: expected YAML mapping at root, got {type(data).__name__}"
        )

    if "inherits" in data:
        data = _resolve_inherits(data, resolved_defaults, source=str(target), chain=[])

    return _parse_instrument_dict(data, source=str(target))


def load_instrument_from_yaml_string(
    yaml_content: str,
    defaults_dir: Path | str | None = None,
    source_name: str = "<string>",
) -> InstrumentConfig:
    """Valider en YAML-streng mot InstrumentConfig-schema.

    Brukes av `bedrock.signal_server.endpoints.rules` for å validere
    bruker-input før skriving til disk. Semantikk-parallell til
    `load_instrument_config`, men uten fil-I/O.

    `source_name` vises i feilmeldinger — default `"<string>"`.
    """
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        raise InstrumentConfigError(f"{source_name}: ugyldig YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise InstrumentConfigError(
            f"{source_name}: expected YAML mapping at root, got {type(data).__name__}"
        )

    resolved_defaults = Path(defaults_dir) if defaults_dir is not None else DEFAULT_DEFAULTS_DIR

    if "inherits" in data:
        data = _resolve_inherits(data, resolved_defaults, source=source_name, chain=[])

    return _parse_instrument_dict(data, source=source_name)


def load_all_instruments(
    directory: Path | str,
    defaults_dir: Path | str | None = None,
) -> dict[str, InstrumentConfig]:
    """Les alle `*.yaml` i katalog og returner som `{instrument.id: config}`.

    `defaults_dir` deles av alle filer — default `config/defaults/`.
    Duplikate IDer kaster `InstrumentConfigError`. Non-YAML-filer og
    underkataloger ignoreres. Tom katalog returnerer tom dict.
    """
    target = Path(directory)
    if not target.exists():
        raise FileNotFoundError(f"Instruments directory not found: {target}")

    result: dict[str, InstrumentConfig] = {}
    for yaml_path in sorted(target.glob("*.yaml")):
        cfg = load_instrument_config(yaml_path, defaults_dir=defaults_dir)
        inst_id = cfg.instrument.id
        if inst_id in result:
            raise InstrumentConfigError(
                f"Duplicate instrument id {inst_id!r} in {yaml_path.name} (also in earlier file)"
            )
        result[inst_id] = cfg

    return result


# ---------------------------------------------------------------------------
# Private: inherits-resolver
# ---------------------------------------------------------------------------


def _resolve_inherits(
    raw: dict[str, Any],
    defaults_dir: Path,
    source: str,
    chain: list[str],
) -> dict[str, Any]:
    """Rekursiv opprulling av `inherits: <parent>` fra `defaults_dir`.

    Regel (shallow merge):

    - `inherits: X` slår opp `defaults_dir/X.yaml`.
    - X kan selv ha `inherits: Y` — opprulles rekursivt.
    - Top-level keys flettes: `{**parent_resolved, **child}` — barnet
      vinner per top-level key. Nested dicts erstatter helt (f.eks. hvis
      barnet definerer `families:`, overtar det hele familie-blokken —
      ingen merging under familie-nivå).
    - `inherits`-nøkkelen slettes fra sluttresultatet.

    Kaster `InstrumentConfigError` ved manglende parent, circular
    inheritance, eller ugyldig YAML-struktur i parent.
    """
    parent_name = raw.get("inherits")
    if parent_name is None:
        # Ingen inherits: ikke noe å gjøre (burde ikke nåes av caller)
        return {k: v for k, v in raw.items() if k != "inherits"}

    if not isinstance(parent_name, str):
        raise InstrumentConfigError(
            f"{source}: `inherits` must be a string, got {type(parent_name).__name__}"
        )

    if parent_name in chain:
        cycle = " → ".join([*chain, parent_name])
        raise InstrumentConfigError(f"{source}: circular inherits chain: {cycle}")

    parent_path = defaults_dir / f"{parent_name}.yaml"
    if not parent_path.exists():
        raise InstrumentConfigError(
            f"{source}: `inherits: {parent_name}` not found at {parent_path}. "
            f"Forventet fil: {defaults_dir}/{parent_name}.yaml"
        )

    with parent_path.open(encoding="utf-8") as f:
        parent_raw = yaml.safe_load(f)

    if not isinstance(parent_raw, dict):
        raise InstrumentConfigError(
            f"{parent_path}: expected YAML mapping at root, got {type(parent_raw).__name__}"
        )

    # Recursively resolve parent's own `inherits` first
    if "inherits" in parent_raw:
        parent_raw = _resolve_inherits(
            parent_raw,
            defaults_dir,
            source=str(parent_path),
            chain=[*chain, parent_name],
        )

    # Shallow merge: child wins on each top-level key
    merged = {**parent_raw, **raw}
    merged.pop("inherits", None)
    return merged


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
        "gates",
    }
)

# Felter som gjelder hver rules-modell. Brukes til å filtrere bort
# irrelevante-for-denne-typen felter som arves fra defaults/base.yaml.
# Eksempel: base.yaml har `horizons` (med entry_tfs/hold-definisjoner
# brukt av setup-generatoren), ikke FinancialRules' `horizons`. For agri
# ignoreres `horizons` helt; for financial ignoreres `max_score`/
# `min_score_publish` (lever per-horisont i HorizonSpec).
_FINANCIAL_RULES_KEYS: frozenset[str] = frozenset(
    {"aggregation", "horizons", "families", "grade_thresholds", "gates"}
)
_AGRI_RULES_KEYS: frozenset[str] = frozenset(
    {
        "aggregation",
        "max_score",
        "min_score_publish",
        "families",
        "grade_thresholds",
        "gates",
    }
)

# Nøkler som er bevisst utsatt til senere session — vi ignorerer dem nå
# uten error slik at YAML-er skrevet for fremtiden ikke bryter i dag.
# `inherits` fjernet session 23: resolves nå av `_resolve_inherits` og
# eksisterer ikke lenger på tidspunkt for `_parse_instrument_dict`.
_DEFERRED_KEYS: frozenset[str] = frozenset(
    {
        "usda_blackout",  # agri-spesifikk kalender-gate — fase 5 senere
        "data_quality",  # base.yaml default — brukes ikke av engine enda
        "hysteresis",  # base.yaml default — forbruk av setups-modulen
    }
)


def _parse_instrument_dict(data: dict[str, Any], source: str) -> InstrumentConfig:
    """Konverter rå YAML-dict til `InstrumentConfig`."""
    if "instrument" not in data:
        raise InstrumentConfigError(f"{source}: missing required 'instrument' block")

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
        filtered = {k: v for k, v in rules_data.items() if k in _FINANCIAL_RULES_KEYS}
        rules = FinancialRules.model_validate(filtered)
    elif aggregation == "additive_sum":
        filtered = {k: v for k, v in rules_data.items() if k in _AGRI_RULES_KEYS}
        rules = AgriRules.model_validate(filtered)
    else:
        raise InstrumentConfigError(
            f"{source}: unknown or missing 'aggregation'. "
            f"Expected 'weighted_horizon' or 'additive_sum', got {aggregation!r}"
        )

    return InstrumentConfig(instrument=metadata, rules=rules)


__all__ = [
    "DEFAULT_DEFAULTS_DIR",
    "InstrumentConfig",
    "InstrumentConfigError",
    "InstrumentMetadata",
    "load_all_instruments",
    "load_instrument_config",
]
