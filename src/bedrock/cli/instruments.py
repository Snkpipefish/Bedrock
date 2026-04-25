"""`bedrock instruments` — inspiser instrument-config fra YAML.

Fase 5 session 22:

- `bedrock instruments list` — viser alle instrumenter i katalogen med
  sentral metadata (id, asset_class, ticker, cot_contract, weather_region,
  antall FRED-serier).
- `bedrock instruments show <id>` — full dump av metadata + aggregation +
  familier/horisont-konfig.
"""

from __future__ import annotations

from pathlib import Path

import click

from bedrock.cli._instrument_lookup import (
    DEFAULT_DEFAULTS_DIR,
    DEFAULT_INSTRUMENTS_DIR,
    find_instrument,
)
from bedrock.config.instruments import (
    InstrumentConfig,
    InstrumentConfigError,
    load_all_instruments,
)
from bedrock.engine.engine import AgriRules, FinancialRules


def _defaults_dir_option(f):
    return click.option(
        "--defaults-dir",
        "defaults_dir",
        default=DEFAULT_DEFAULTS_DIR,
        show_default=True,
        type=click.Path(path_type=Path),
        help="Katalog med defaults-YAML-er (brukt av `inherits:`).",
    )(f)


@click.group()
def instruments() -> None:
    """Inspiser instrument-konfigurasjoner i config/instruments/."""


@instruments.command("list")
@click.option(
    "--instruments-dir",
    "instruments_dir",
    default=DEFAULT_INSTRUMENTS_DIR,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Katalog med instrument-YAML-er.",
)
@_defaults_dir_option
def list_cmd(instruments_dir: Path, defaults_dir: Path) -> None:
    """List alle instrumenter i katalog med sentral metadata."""
    if not instruments_dir.exists():
        raise click.UsageError(f"Instruments directory not found: {instruments_dir}")

    try:
        configs = load_all_instruments(instruments_dir, defaults_dir=defaults_dir)
    except InstrumentConfigError as exc:
        raise click.UsageError(f"Kunne ikke laste instrumenter: {exc}") from exc

    if not configs:
        click.echo(f"(ingen instrumenter i {instruments_dir})")
        return

    header = (
        f"{'id':<12} {'asset_class':<10} {'ticker':<10} {'cot_contract':<40} {'weather':<15} fred"
    )
    click.echo(header)
    click.echo("-" * len(header))
    for inst_id in sorted(configs.keys()):
        cfg = configs[inst_id]
        meta = cfg.instrument
        cot = meta.cot_contract or "-"
        weather = meta.weather_region or "-"
        fred_count = len(meta.fred_series_ids)
        click.echo(
            f"{meta.id:<12} {meta.asset_class:<10} {meta.ticker:<10} "
            f"{cot[:40]:<40} {weather[:15]:<15} {fred_count}"
        )


@instruments.command("show")
@click.argument("instrument_id")
@click.option(
    "--instruments-dir",
    "instruments_dir",
    default=DEFAULT_INSTRUMENTS_DIR,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Katalog med instrument-YAML-er.",
)
@_defaults_dir_option
def show_cmd(instrument_id: str, instruments_dir: Path, defaults_dir: Path) -> None:
    """Vis full config for ett instrument (metadata + rules-oversikt)."""
    cfg = find_instrument(instrument_id, instruments_dir, defaults_dir=defaults_dir)
    _print_instrument(cfg)


def _print_instrument(cfg: InstrumentConfig) -> None:
    meta = cfg.instrument
    click.echo(f"instrument: {meta.id}")
    click.echo(f"  asset_class:     {meta.asset_class}")
    click.echo(f"  ticker:          {meta.ticker}")
    click.echo(f"  cfd_ticker:      {meta.cfd_ticker or '-'}")
    click.echo(f"  yahoo_ticker:    {meta.yahoo_ticker or '-'}")
    click.echo(f"  cot_contract:    {meta.cot_contract or '-'}")
    click.echo(f"  cot_report:      {meta.cot_report or '-'}")
    click.echo(f"  weather_region:  {meta.weather_region or '-'}")
    if meta.weather_lat is not None and meta.weather_lon is not None:
        click.echo(f"  weather_coords:  ({meta.weather_lat}, {meta.weather_lon})")
    if meta.fred_series_ids:
        click.echo(f"  fred_series_ids: {meta.fred_series_ids}")
    else:
        click.echo("  fred_series_ids: []")

    click.echo("")
    rules = cfg.rules
    click.echo(f"rules.aggregation: {rules.aggregation}")
    if isinstance(rules, FinancialRules):
        click.echo(f"  horizons: {sorted(rules.horizons.keys())}")
        families: set[str] = set()
        for hspec in rules.horizons.values():
            families.update(hspec.family_weights.keys())
        click.echo(f"  families (across horizons): {sorted(families)}")
    elif isinstance(rules, AgriRules):
        click.echo(f"  max_score: {rules.max_score}")
        click.echo(f"  min_score_publish: {rules.min_score_publish}")
        click.echo(f"  families: {sorted(rules.families.keys())}")


__all__ = ["instruments"]
