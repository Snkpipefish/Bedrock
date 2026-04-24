"""Bot-config-lasting med SIGHUP-reload-støtte.

Per bruker-beslutning (session 39, se `docs/migration/bot_refactor.md § 10.3`):
`config/bot.yaml` splittes i to top-level seksjoner:

- **`startup_only`** — krever prosess-restart. SIGHUP logger advarsel hvis
  disse er endret i YAML, men beholder gamle verdier aktive.
- **`reloadable`** — SIGHUP plukker opp endringer umiddelbart.

Eksempler per seksjon:
    startup_only:
      signal_url: "http://localhost:5100"
      reconnect:
        window_sec: 600
        max_in_window: 5
    reloadable:
      confirmation:
        min_score_default: 2
        body_threshold_atr_pct: 0.30
        ...

`load_bot_config(path)` brukes ved oppstart. `reload_bot_config(path, current)`
brukes fra SIGHUP-handler: returnerer (ny config, liste av startup_only-
diff-meldinger). Caller logger diff-ene og erstatter kun `reloadable`-delen
atomisk slik at pågående trades ikke ser halv-oppdatert state.

Fil-sti-oppløsning:
  1. Eksplisitt argument til `load_bot_config(path)`
  2. Env-var `BEDROCK_BOT_CONFIG`
  3. Default: `<repo>/config/bot.yaml`
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ReconnectConfig(BaseModel):
    """cTrader reconnect-budsjett (startup_only)."""

    window_sec: int = 600
    max_in_window: int = 5

    model_config = ConfigDict(extra="forbid")


class StartupOnlyConfig(BaseModel):
    """Felter som krever bot-restart for å aktivere endring.

    SIGHUP-reload vil logge advarsel hvis disse endres i YAML og beholde
    gamle verdier til neste prosess-restart.
    """

    signal_url: str = "http://localhost:5100"
    signal_api_key_env: str = "SCALP_API_KEY"  # env-var-navn, ikke selve nøkkelen
    reconnect: ReconnectConfig = Field(default_factory=ReconnectConfig)

    model_config = ConfigDict(extra="forbid")


class ConfirmationConfig(BaseModel):
    """3-punkt confirmation-terskler (reloadable)."""

    min_score_default: int = 2
    max_candles_default: int = 6
    body_threshold_atr_pct: float = 0.30
    ema_gradient_buy_min: float = -0.05
    ema_gradient_sell_max: float = 0.05

    model_config = ConfigDict(extra="forbid")


class RiskPctConfig(BaseModel):
    """Risk-% tier for position sizing (reloadable)."""

    full: float = 1.0
    half: float = 0.5
    quarter: float = 0.25

    model_config = ConfigDict(extra="forbid")


class DailyLossConfig(BaseModel):
    """Daily-loss-gate (reloadable). `max(pct_of_balance, minimum_nok)`."""

    pct_of_balance: float = 2.0
    minimum_nok: float = 500

    model_config = ConfigDict(extra="forbid")


class SpreadConfig(BaseModel):
    """Spread-filter (reloadable)."""

    min_samples: int = 10
    agri_multiplier: float = 2.5
    non_agri_multiplier_of_stop: float = 2.0  # mult × stop_multiplier

    model_config = ConfigDict(extra="forbid")


class HorizonTTLConfig(BaseModel):
    """Per-horisont TTL i sekunder (reloadable)."""

    scalp: int = 15 * 60
    swing: int = 4 * 60 * 60
    makro: int = 24 * 60 * 60

    model_config = ConfigDict(extra="forbid")


class HorizonMinRRConfig(BaseModel):
    """Per-horisont minimum R:R-gate (reloadable)."""

    scalp: float = 1.0
    swing: float = 1.3
    makro: float = 1.5

    model_config = ConfigDict(extra="forbid")


class PollingConfig(BaseModel):
    """Signal-server-polling (reloadable)."""

    default_seconds: int = 60
    scalp_active_seconds: int = 20

    model_config = ConfigDict(extra="forbid")


class WeekendConfig(BaseModel):
    """Fredag-lukke-regel (reloadable)."""

    sl_atr_mult: float = 1.5

    model_config = ConfigDict(extra="forbid")


class MondayGapConfig(BaseModel):
    """Mandags-åpnings-gap-gate (reloadable)."""

    atr_multiplier: float = 2.0

    model_config = ConfigDict(extra="forbid")


class TrailConfig(BaseModel):
    """Trailing-stop fallback (reloadable). Group-spesifikke verdier i `group_params`."""

    default_atr_mult: float = 1.5

    model_config = ConfigDict(extra="forbid")


class AgriSessionTime(BaseModel):
    """Åpningstider i CET/CEST for ett agri-instrument."""

    start: str  # "HH:MM"
    end: str  # "HH:MM"

    model_config = ConfigDict(extra="forbid")


class AgriConfig(BaseModel):
    """Agri-spesifikke begrensninger (reloadable)."""

    max_concurrent: int = 2
    max_per_subgroup: int = 1
    max_spread_atr_ratio: float = 0.40
    session_times_cet: dict[str, AgriSessionTime] = Field(
        default_factory=lambda: {
            "corn": AgriSessionTime(start="09:00", end="21:00"),
            "wheat": AgriSessionTime(start="09:00", end="21:00"),
            "soybean": AgriSessionTime(start="09:00", end="21:00"),
            "coffee": AgriSessionTime(start="09:00", end="19:30"),
            "cotton": AgriSessionTime(start="09:00", end="20:00"),
            "sugar": AgriSessionTime(start="09:00", end="19:30"),
            "cocoa": AgriSessionTime(start="09:00", end="19:30"),
        }
    )

    model_config = ConfigDict(extra="forbid")


class OilConfig(BaseModel):
    """Oil-spesifikke gate-verdier (reloadable)."""

    min_sl_pips: int = 25
    max_spread_mult: float = 3.0

    model_config = ConfigDict(extra="forbid")


class GroupParams(BaseModel):
    """Per-gruppe exit-/management-parametre (reloadable).

    Brukes av exit-logikk via `bot.instruments.get_group_name(instrument)`
    → `reloadable.group_params[group_name]`.
    """

    trail_atr: float
    gb_peak: float  # giveback peak-threshold (0-1)
    gb_exit: float  # giveback exit-threshold (0-1)
    be_atr: float  # break-even atr-ratio
    expiry: int  # expiry_candles (15m-enheter)
    ema9_exit: bool  # P4 EMA9-exit aktiv?

    model_config = ConfigDict(extra="forbid")


def _default_group_params() -> dict[str, GroupParams]:
    """Defaults fra trading_bot.py:268-283."""
    return {
        "fx": GroupParams(
            trail_atr=2.5, gb_peak=0.85, gb_exit=0.30, be_atr=0.10, expiry=32, ema9_exit=True
        ),
        "gold": GroupParams(
            trail_atr=3.5, gb_peak=0.90, gb_exit=0.45, be_atr=0.25, expiry=48, ema9_exit=False
        ),
        "silver": GroupParams(
            trail_atr=3.5, gb_peak=0.88, gb_exit=0.42, be_atr=0.25, expiry=48, ema9_exit=False
        ),
        "oil": GroupParams(
            trail_atr=3.0, gb_peak=0.90, gb_exit=0.45, be_atr=0.20, expiry=48, ema9_exit=False
        ),
        "indices": GroupParams(
            trail_atr=2.8, gb_peak=0.85, gb_exit=0.35, be_atr=0.15, expiry=40, ema9_exit=True
        ),
        "corn": GroupParams(
            trail_atr=2.0, gb_peak=0.85, gb_exit=0.35, be_atr=0.20, expiry=48, ema9_exit=True
        ),
        "wheat": GroupParams(
            trail_atr=2.0, gb_peak=0.85, gb_exit=0.35, be_atr=0.20, expiry=48, ema9_exit=True
        ),
        "soybean": GroupParams(
            trail_atr=2.0, gb_peak=0.85, gb_exit=0.35, be_atr=0.20, expiry=48, ema9_exit=True
        ),
        "coffee": GroupParams(
            trail_atr=2.5, gb_peak=0.88, gb_exit=0.35, be_atr=0.20, expiry=48, ema9_exit=True
        ),
        "cocoa": GroupParams(
            trail_atr=2.5, gb_peak=0.88, gb_exit=0.35, be_atr=0.20, expiry=48, ema9_exit=True
        ),
        "sugar": GroupParams(
            trail_atr=2.5, gb_peak=0.88, gb_exit=0.35, be_atr=0.20, expiry=48, ema9_exit=True
        ),
        "cotton": GroupParams(
            trail_atr=2.5, gb_peak=0.88, gb_exit=0.35, be_atr=0.20, expiry=48, ema9_exit=True
        ),
    }


class ReloadableConfig(BaseModel):
    """Felter som SIGHUP kan oppdatere uten bot-restart."""

    confirmation: ConfirmationConfig = Field(default_factory=ConfirmationConfig)
    risk_pct: RiskPctConfig = Field(default_factory=RiskPctConfig)
    daily_loss: DailyLossConfig = Field(default_factory=DailyLossConfig)
    spread: SpreadConfig = Field(default_factory=SpreadConfig)
    horizon_ttl: HorizonTTLConfig = Field(default_factory=HorizonTTLConfig)
    horizon_min_rr: HorizonMinRRConfig = Field(default_factory=HorizonMinRRConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    weekend: WeekendConfig = Field(default_factory=WeekendConfig)
    monday_gap: MondayGapConfig = Field(default_factory=MondayGapConfig)
    trail: TrailConfig = Field(default_factory=TrailConfig)
    agri: AgriConfig = Field(default_factory=AgriConfig)
    oil: OilConfig = Field(default_factory=OilConfig)
    group_params: dict[str, GroupParams] = Field(default_factory=_default_group_params)

    model_config = ConfigDict(extra="forbid")


class BotConfig(BaseModel):
    """Full bot-config: startup_only + reloadable."""

    startup_only: StartupOnlyConfig = Field(default_factory=StartupOnlyConfig)
    reloadable: ReloadableConfig = Field(default_factory=ReloadableConfig)

    model_config = ConfigDict(extra="forbid")


# ─────────────────────────────────────────────────────────────
# Path-oppløsning og lasting
# ─────────────────────────────────────────────────────────────

DEFAULT_BOT_CONFIG_PATH = Path("config/bot.yaml")


def resolve_bot_config_path(path: Path | str | None = None) -> Path:
    """Returner faktisk sti til bot.yaml.

    Rekkefølge:
      1. Eksplisitt argument
      2. Env-var `BEDROCK_BOT_CONFIG`
      3. `config/bot.yaml` relativ til cwd
    """
    if path is not None:
        return Path(path)
    env = os.environ.get("BEDROCK_BOT_CONFIG")
    if env:
        return Path(env)
    return DEFAULT_BOT_CONFIG_PATH


def load_bot_config(path: Path | str | None = None) -> BotConfig:
    """Last bot-config fra YAML-fil.

    Tomme/manglende seksjoner faller tilbake til Pydantic-defaults, slik
    at brukeren kan ha en minimal `bot.yaml` som kun overstyrer det hen
    vil justere.
    """
    actual = resolve_bot_config_path(path)
    if not actual.exists():
        # Ingen YAML → bruk defaults. Logging gjøres av caller (vet loggernavn).
        return BotConfig()
    text = actual.read_text(encoding="utf-8")
    return load_bot_config_from_yaml_string(text)


def load_bot_config_from_yaml_string(text: str) -> BotConfig:
    """Parse en YAML-streng til BotConfig. Tom streng → defaults."""
    data: Any = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"bot.yaml top-level må være mapping, fikk {type(data).__name__}"
        )
    return BotConfig.model_validate(data)


# ─────────────────────────────────────────────────────────────
# SIGHUP-reload
# ─────────────────────────────────────────────────────────────


def diff_startup_only(
    current: StartupOnlyConfig, proposed: StartupOnlyConfig
) -> list[str]:
    """Returner liste av felt-paths som er endret i `proposed` vs `current`.

    Returnerer tom liste hvis identiske. Feilmelding er egnet for å logge
    ved SIGHUP: brukeren kan se hva som trengs restart for å aktivere.
    """
    diffs: list[str] = []
    cur_dict = current.model_dump()
    new_dict = proposed.model_dump()
    _walk_diff(cur_dict, new_dict, prefix="startup_only", out=diffs)
    return diffs


def _walk_diff(
    cur: Any, new: Any, *, prefix: str, out: list[str]
) -> None:
    if isinstance(cur, dict) and isinstance(new, dict):
        keys = set(cur.keys()) | set(new.keys())
        for k in sorted(keys):
            _walk_diff(cur.get(k), new.get(k), prefix=f"{prefix}.{k}", out=out)
        return
    if cur != new:
        out.append(f"{prefix}: {cur!r} → {new!r}")


def apply_reloadable_inplace(
    current: ReloadableConfig, new: ReloadableConfig
) -> None:
    """Muter `current` in-place til å matche `new`'s felter.

    Trengs av SIGHUP-handleren i `bot/__main__.py`: alle bot-moduler
    holder samme ReloadableConfig-instans via `self._config`. I stedet
    for å bytte ut referansen overalt (krever full module-graph-
    oppdatering), oppdaterer vi feltene på plass. Pydantic v2 støtter
    `__setattr__` på BaseModel så lenge ikke `frozen=True`.
    """
    for name in type(new).model_fields:
        setattr(current, name, getattr(new, name))


def reload_bot_config(
    path: Path | str | None, current: BotConfig
) -> tuple[BotConfig, list[str]]:
    """SIGHUP-reload-entry.

    Leser YAML på nytt, holder `current.startup_only` aktiv og bytter
    kun ut `reloadable`-delen. Returnerer:

    - `new_config`: aktiv config etter reload (startup_only = current,
      reloadable = ny)
    - `startup_only_diffs`: liste av felt-paths som ble endret i YAML men
      ikke aktivert — caller bør logge disse som warning.

    Hvis YAML-filen mangler, returneres `(current, [])`.
    """
    proposed = load_bot_config(path)
    diffs = diff_startup_only(current.startup_only, proposed.startup_only)
    merged = BotConfig(
        startup_only=current.startup_only,
        reloadable=proposed.reloadable,
    )
    return merged, diffs
