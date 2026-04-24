"""`bedrock systemd` — generer + installer systemd-unit-filer.

Fase 6 session 30: bruker systemd istedenfor egen daemon. CLI:

- `bedrock systemd generate` — leser `config/fetch.yaml` og skriver
  `.service` + `.timer`-filer til `systemd/`-mappen.
- `bedrock systemd install` — kjører `systemctl --user link` for hver
  genererte unit-fil.
- `bedrock systemd list` — viser hvilke unit-filer som er generert.

`install` er bevisst minimalistisk: den kun `link`-er slik at brukeren
selv kan `systemctl --user enable --now bedrock-fetch-<name>.timer`
etter inspeksjon. Ingen auto-enable i session 30.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import click

from bedrock.config.fetch import (
    DEFAULT_FETCH_CONFIG_PATH,
    FetchConfigError,
    load_fetch_config,
)
from bedrock.systemd.generator import (
    CronConversionError,
    generate_units,
    write_units,
)

DEFAULT_UNITS_DIR = Path("systemd")


@click.group()
def systemd() -> None:
    """Generer og installer systemd-unit-filer fra fetch-config."""


@systemd.command("generate")
@click.option(
    "--config",
    "config_path",
    default=DEFAULT_FETCH_CONFIG_PATH,
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--output",
    "output_dir",
    default=DEFAULT_UNITS_DIR,
    show_default=True,
    type=click.Path(path_type=Path),
    help="Katalog hvor `.service`/`.timer`-filer skrives.",
)
@click.option(
    "--working-dir",
    "working_dir",
    default=None,
    type=click.Path(path_type=Path),
    help=(
        "WorkingDirectory i genererte .service-filer. "
        "Default: gjeldende arbeidskatalog."
    ),
)
@click.option(
    "--executable",
    "bedrock_executable",
    default=None,
    help=(
        "Full sti til `bedrock`-CLI som systemd skal kjøre. "
        "Default: detect fra `sys.executable`."
    ),
)
def generate_cmd(
    config_path: Path,
    output_dir: Path,
    working_dir: Path | None,
    bedrock_executable: str | None,
) -> None:
    """Generer `.service` + `.timer`-filer fra fetch.yaml."""
    try:
        config = load_fetch_config(config_path)
    except FileNotFoundError as exc:
        raise click.UsageError(str(exc)) from exc
    except FetchConfigError as exc:
        raise click.UsageError(str(exc)) from exc

    resolved_working = working_dir.resolve() if working_dir else Path.cwd()
    resolved_executable = bedrock_executable or _detect_bedrock_executable()

    try:
        units = generate_units(
            config,
            working_dir=resolved_working,
            bedrock_executable=resolved_executable,
        )
    except CronConversionError as exc:
        raise click.UsageError(f"cron-konverteringsfeil: {exc}") from exc

    written = write_units(units, output_dir)

    click.echo(
        f"Skrev {len(written)} filer til {output_dir.resolve()}:"
    )
    for path in written:
        click.echo(f"  {path.name}")
    click.echo("")
    click.echo("Neste steg:")
    click.echo(f"  bedrock systemd install --units-dir {output_dir}")
    click.echo(
        "  # deretter: systemctl --user enable --now "
        "bedrock-fetch-<name>.timer"
    )


@systemd.command("install")
@click.option(
    "--units-dir",
    "units_dir",
    default=DEFAULT_UNITS_DIR,
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Vis kommandoene som ville blitt kjørt, uten å kjøre dem.",
)
def install_cmd(units_dir: Path, dry_run: bool) -> None:
    """Kjør `systemctl --user link` på alle genererte unit-filer.

    Filene lenkes inn i `~/.config/systemd/user/` slik at systemd finner
    dem. Etter install må brukeren selv `systemctl --user enable --now
    <timer>` for å starte.
    """
    if not units_dir.exists():
        raise click.UsageError(
            f"Units-katalog mangler: {units_dir}. Kjør "
            f"`bedrock systemd generate` først."
        )

    units = sorted(units_dir.glob("bedrock-fetch-*"))
    if not units:
        raise click.UsageError(
            f"Fant ingen bedrock-fetch-* filer i {units_dir}"
        )

    systemctl = shutil.which("systemctl")
    if systemctl is None and not dry_run:
        raise click.UsageError(
            "Fant ikke `systemctl`. Denne kommandoen krever systemd."
        )

    any_failure = False
    for unit in units:
        cmd = [
            systemctl or "systemctl",
            "--user",
            "link",
            str(unit.resolve()),
        ]
        if dry_run:
            click.echo(f"DRY-RUN  {' '.join(cmd)}")
            continue

        click.echo(f"link {unit.name}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            click.echo(f"  FAIL: {result.stderr.strip()}", err=True)
            any_failure = True
        else:
            # systemctl link har ofte ingen stdout ved suksess
            if result.stdout.strip():
                click.echo(f"  {result.stdout.strip()}")

    if not dry_run:
        click.echo("")
        click.echo(
            "Kjør `systemctl --user daemon-reload` hvis enheter ikke "
            "vises automatisk."
        )
        click.echo(
            "Aktiver timere med: "
            "systemctl --user enable --now bedrock-fetch-<name>.timer"
        )

    if any_failure:
        click.get_current_context().exit(1)


@systemd.command("list")
@click.option(
    "--units-dir",
    "units_dir",
    default=DEFAULT_UNITS_DIR,
    show_default=True,
    type=click.Path(path_type=Path),
)
def list_cmd(units_dir: Path) -> None:
    """List genererte unit-filer og deres OnCalendar-tidspunkter."""
    if not units_dir.exists():
        click.echo(f"(katalog mangler: {units_dir})")
        return

    timers = sorted(units_dir.glob("bedrock-fetch-*.timer"))
    services = sorted(units_dir.glob("bedrock-fetch-*.service"))
    click.echo(f"Enheter i {units_dir}: {len(timers)} timer(e), {len(services)} service(s)")
    click.echo("")

    for timer in timers:
        content = timer.read_text()
        oncal = _extract_oncalendar(content)
        click.echo(f"  {timer.name}")
        click.echo(f"    OnCalendar={oncal}")


def _extract_oncalendar(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("OnCalendar="):
            return line.split("=", 1)[1]
    return "(ikke funnet)"


def _detect_bedrock_executable() -> str:
    """Detect hvilken bedrock-CLI som skal kjøres av systemd.

    Preferanse:
    1. `<sys.prefix>/bin/bedrock` hvis den finnes (typisk `.venv/bin/bedrock`)
    2. `shutil.which('bedrock')` på PATH
    3. Fallback: `sys.executable -m bedrock.cli`
    """
    venv_bedrock = Path(sys.prefix) / "bin" / "bedrock"
    if venv_bedrock.exists():
        return str(venv_bedrock)

    path_bedrock = shutil.which("bedrock")
    if path_bedrock is not None:
        return path_bedrock

    return f"{sys.executable} -m bedrock.cli"


__all__ = ["systemd"]
