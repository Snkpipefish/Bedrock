"""Systemd-integrasjon for Bedrock.

Fase 6 session 30: generator for `.timer` + `.service`-unit-filer fra
`config/fetch.yaml`. Ingen daemon — systemd tar jobben.

Hovedfunksjonalitet:

- `cron_to_oncalendar(cron_expr)`: oversetter standard 5-felt cron-
  uttrykk til systemd `OnCalendar=`-syntaks.
- `generate_units(fetch_config, *, working_dir, bedrock_executable)`:
  returner `{filename: content}` for alle fetchere i config.
- `write_units(units, output_dir)`: skriv til disk.

CLI: `bedrock systemd generate|install|list` (se `bedrock.cli.systemd`).
"""

from __future__ import annotations

from bedrock.systemd.generator import (
    UNIT_FILENAME_PREFIX,
    cron_to_oncalendar,
    generate_service_unit,
    generate_timer_unit,
    generate_units,
    write_units,
)

__all__ = [
    "UNIT_FILENAME_PREFIX",
    "cron_to_oncalendar",
    "generate_service_unit",
    "generate_timer_unit",
    "generate_units",
    "write_units",
]
