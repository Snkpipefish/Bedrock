"""Generer systemd `.timer` + `.service`-unit-filer fra fetch-config.

Én fetcher → én `bedrock-fetch-<name>.service` + én `bedrock-fetch-
<name>.timer`. Systemd kjører. Ingen Python-daemon.

Cron-til-OnCalendar:

    "40 * * * 1-5"    → "Mon-Fri *-*-* *:40:00"
    "0 22 * * 5"      → "Fri *-*-* 22:00:00"
    "30 2 * * *"      → "*-*-* 02:30:00"
    "0 3 * * *"       → "*-*-* 03:00:00"

Ikke-støttet syntaks (enn så lenge):
- `*/N` step-values
- `L`/`W`/`#`-suffikser
- Named dag (JAN-DEC, MON-SUN i cron-feltet)

Gir tydelig `CronConversionError` i disse tilfellene. Utvides når
faktisk behov oppstår.
"""

from __future__ import annotations

from pathlib import Path

from bedrock.config.fetch import FetchConfig

UNIT_FILENAME_PREFIX = "bedrock-fetch-"


# ---------------------------------------------------------------------------
# Cron → OnCalendar
# ---------------------------------------------------------------------------


class CronConversionError(ValueError):
    """Cron-uttrykk kan ikke konverteres til OnCalendar-format."""


_DOW_MAP = {
    0: "Sun",
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",  # standard cron tillater både 0 og 7 for søndag
}


def cron_to_oncalendar(cron_expr: str) -> str:
    """Oversett 5-felt cron-uttrykk til systemd OnCalendar-streng.

    Format på cron: `minute hour dom month dow`.
    Format på output: `[DOW ]YYYY-MM-DD hh:mm:ss`, der hvert felt kan være
    `*` eller en spesifikk verdi.

    Reiser `CronConversionError` for ikke-støttet syntaks.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise CronConversionError(
            f"cron må ha 5 felter (minute hour dom month dow), fikk {len(parts)}: {cron_expr!r}"
        )
    minute, hour, dom, month, dow = parts

    _reject_unsupported(minute, "minute", cron_expr)
    _reject_unsupported(hour, "hour", cron_expr)
    _reject_unsupported(dom, "dom", cron_expr)
    _reject_unsupported(month, "month", cron_expr)
    _reject_unsupported(dow, "dow", cron_expr)

    minute_s = _field_to_systemd_time(minute, field="minute")
    hour_s = _field_to_systemd_time(hour, field="hour")
    dom_s = _field_to_systemd_date(dom)
    month_s = _field_to_systemd_date(month, zero_pad=True)
    dow_s = _dow_to_systemd(dow)

    date_part = f"*-{month_s}-{dom_s}"
    time_part = f"{hour_s}:{minute_s}:00"

    if dow_s:
        return f"{dow_s} {date_part} {time_part}"
    return f"{date_part} {time_part}"


def _reject_unsupported(value: str, name: str, expr: str) -> None:
    """Fanger step- og navnebaserte felter vi ikke håndterer."""
    if "/" in value:
        raise CronConversionError(
            f"step-values ({value!r}) i {name}-felt er ikke støttet i "
            f"MVP-konverteren. cron={expr!r}"
        )
    # Named months/dows ("JAN", "MON" osv.) — noen cron-implementasjoner
    # støtter det, men vi krever numerisk for MVP.
    if any(c.isalpha() for c in value):
        raise CronConversionError(
            f"named {name}-felter ({value!r}) er ikke støttet; bruk numerisk form. cron={expr!r}"
        )


def _field_to_systemd_time(value: str, *, field: str) -> str:
    """Konverter minute/hour-felt: `*` → `*`, tall → nullpadded tall."""
    if value == "*":
        return "*"
    if "," in value or "-" in value:
        raise CronConversionError(f"range/list i {field}-felt ikke støttet i MVP: {value!r}")
    return f"{int(value):02d}"


def _field_to_systemd_date(field: str, *, zero_pad: bool = False) -> str:
    """Konverter dom/month-felt: `*` → `*`, tall → tall (valgfritt padd)."""
    if field == "*":
        return "*"
    if "," in field or "-" in field:
        raise CronConversionError(f"range/list i dom/month-felt ikke støttet i MVP: {field!r}")
    n = int(field)
    return f"{n:02d}" if zero_pad else str(n)


def _dow_to_systemd(field: str) -> str:
    """Konverter dow-felt til systemd DOW-prefix. Tom streng hvis `*`."""
    if field == "*":
        return ""
    if "-" in field:
        start, end = field.split("-", maxsplit=1)
        return f"{_dow_map(start)}-{_dow_map(end)}"
    if "," in field:
        parts = field.split(",")
        return ",".join(_dow_map(p) for p in parts)
    return _dow_map(field)


def _dow_map(value: str) -> str:
    try:
        n = int(value)
    except ValueError as exc:
        raise CronConversionError(f"ugyldig dow-verdi: {value!r}") from exc
    if n not in _DOW_MAP:
        raise CronConversionError(f"dow utenfor 0-7: {value!r}")
    return _DOW_MAP[n]


# ---------------------------------------------------------------------------
# Unit-generering
# ---------------------------------------------------------------------------


def generate_service_unit(
    fetcher_name: str,
    *,
    working_dir: Path | str,
    bedrock_executable: str,
    module_hint: str = "",
) -> str:
    """Bygg .service-innhold for én fetcher.

    `bedrock_executable` er full path til `bedrock`-CLI-en, typisk
    `<repo>/.venv/bin/bedrock` eller `uv run bedrock`. Caller avgjør.
    """
    description = f"Bedrock fetch: {fetcher_name}"
    if module_hint:
        description += f" ({module_hint})"

    return (
        "# Auto-generert av `bedrock systemd generate`.\n"
        "# Ikke rediger manuelt — kjør CLI-kommandoen på nytt hvis config endrer seg.\n"
        "[Unit]\n"
        f"Description={description}\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"WorkingDirectory={working_dir}\n"
        f"ExecStart={bedrock_executable} fetch run {fetcher_name}\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def generate_timer_unit(
    fetcher_name: str,
    cron_expr: str,
    *,
    persistent: bool = True,
) -> str:
    """Bygg .timer-innhold for én fetcher.

    `persistent=True` sørger for at hvis maskinen var av ved fire-tid,
    kjøres unit-en ved neste boot — kritisk for å unngå gap.
    """
    on_calendar = cron_to_oncalendar(cron_expr)
    service_name = f"{UNIT_FILENAME_PREFIX}{fetcher_name}.service"

    return (
        "# Auto-generert av `bedrock systemd generate`.\n"
        "# Ikke rediger manuelt — kjør CLI-kommandoen på nytt hvis config endrer seg.\n"
        "[Unit]\n"
        f"Description=Bedrock fetch timer: {fetcher_name}\n"
        f"Requires={service_name}\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar={on_calendar}\n"
        f"Persistent={'true' if persistent else 'false'}\n"
        f"Unit={service_name}\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def generate_units(
    config: FetchConfig,
    *,
    working_dir: Path | str,
    bedrock_executable: str,
) -> dict[str, str]:
    """Returner `{filename: content}` for alle fetchere i config.

    Filnavn:
    - `bedrock-fetch-<name>.service`
    - `bedrock-fetch-<name>.timer`
    """
    units: dict[str, str] = {}
    for name, spec in sorted(config.fetchers.items()):
        service_file = f"{UNIT_FILENAME_PREFIX}{name}.service"
        timer_file = f"{UNIT_FILENAME_PREFIX}{name}.timer"
        units[service_file] = generate_service_unit(
            name,
            working_dir=working_dir,
            bedrock_executable=bedrock_executable,
            module_hint=spec.module,
        )
        units[timer_file] = generate_timer_unit(name, spec.cron)
    return units


def write_units(units: dict[str, str], output_dir: Path | str) -> list[Path]:
    """Skriv alle unit-filer til `output_dir`. Returner sortert liste."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, content in sorted(units.items()):
        out = target / filename
        out.write_text(content, encoding="utf-8")
        written.append(out)
    return written


__all__ = [
    "UNIT_FILENAME_PREFIX",
    "CronConversionError",
    "cron_to_oncalendar",
    "generate_service_unit",
    "generate_timer_unit",
    "generate_units",
    "write_units",
]
