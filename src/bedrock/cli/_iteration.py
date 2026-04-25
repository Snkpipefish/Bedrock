"""Felles iterasjons-mønster for CLI-kommandoer med multi-item backfill.

Prinsipp (fra Fase 5 session 22):

- `--instrument X` uten eksplisitt item-arg itererer over alle items
  X trenger (f.eks. alle FRED-serier).
- Per-item progress-utskrift.
- Én feil stopper ikke hele jobben — fortsett og samle opp feil.
- Ved feil: print oppsummering med ferdig-formaterte retry-kommandoer.
- Exit-kode != 0 hvis minst én feil.

Generaliseres til alle backfill-subkommandoer for konsistent UX.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import click


@dataclass
class ItemResult:
    """Resultat av én item-backfill i en iterasjon."""

    item_id: str
    ok: bool
    rows_written: int = 0
    error: str | None = None


def run_with_summary(
    items: Sequence[str],
    process_fn: Callable[[str], int],
    retry_command: Callable[[str], str],
    label: str = "item",
) -> list[ItemResult]:
    """Kjør `process_fn(item)` for hver item, med per-item progress + samlet
    summering.

    - `process_fn(item_id)` skal returnere antall rader skrevet. Kastede
      exceptions fanges, registreres, og iterasjonen fortsetter.
    - `retry_command(item_id)` skal returnere en ferdig copy-paste-bar
      kommando for å re-kjøre akkurat den itemen.
    - Etter iterasjon printes oppsummering til stdout (stderr for feil).
    - Ved minst én feil kalles `ctx.exit(1)` slik at exit-kode reflekterer
      status for skript-integrering.

    Returnerer liste av `ItemResult` for videre bruk (tester, programmer).
    """
    results: list[ItemResult] = []
    total = len(items)
    for idx, item in enumerate(items, start=1):
        click.echo(f"[{idx}/{total}] {label}={item}")
        try:
            written = process_fn(item)
        except Exception as exc:
            results.append(ItemResult(item_id=item, ok=False, error=str(exc)))
            click.echo(f"  FAIL {item}: {exc}", err=True)
            continue
        results.append(ItemResult(item_id=item, ok=True, rows_written=written))
        click.echo(f"  OK   {item} → {written} row(s)")

    _print_summary(results, retry_command, label)

    if any(not r.ok for r in results):
        ctx = click.get_current_context(silent=True)
        if ctx is not None:
            ctx.exit(1)

    return results


def _print_summary(
    results: list[ItemResult],
    retry_command: Callable[[str], str],
    label: str,
) -> None:
    ok = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    total_rows = sum(r.rows_written for r in ok)

    if len(results) <= 1 and not failed:
        # 1-item success: unngå støyende summary-seksjon.
        return

    click.echo("")
    click.echo(
        f"=== Summary: {len(ok)}/{len(results)} ok, {len(failed)} failed, "
        f"{total_rows} total row(s) ==="
    )

    if failed:
        click.echo("Failed items:", err=True)
        for r in failed:
            click.echo(f"  {label}={r.item_id}: {r.error}", err=True)
        click.echo("", err=True)
        click.echo("Retry failed items with:", err=True)
        for r in failed:
            click.echo(f"  {retry_command(r.item_id)}", err=True)


__all__ = ["ItemResult", "run_with_summary"]
