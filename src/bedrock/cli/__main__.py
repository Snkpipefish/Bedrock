"""Bedrock CLI entry-point.

    bedrock backfill prices --instrument Gold --ticker xauusd --from 2016-01-01

pyproject.toml mapper `bedrock`-kommandoen til `bedrock.cli.__main__:cli`.
Under utvikling kan `python -m bedrock.cli` brukes i stedet.
"""

from __future__ import annotations

import logging

import click

from bedrock.cli.backfill import backfill


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Aktiver DEBUG-logging.")
def cli(verbose: bool) -> None:
    """Bedrock — config-drevet trading-system."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


cli.add_command(backfill)


if __name__ == "__main__":
    cli()
