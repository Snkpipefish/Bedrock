"""Smoke-test for `systemd/bedrock-bot.service` (sub-fase 12.9 D4).

Verifiserer at unit-fila eksisterer i repoet og inneholder de kritiske
nøkkel-verdiene fra PLAN § 21.6. Filen lenkes manuelt inn av operatør
(`systemctl --user link <repo>/systemd/bedrock-bot.service`); auto-
generator-CLI håndterer kun fetch-* per nå.

Disse verdiene er sikkerhets-kritiske:
- RestartPreventExitStatus=78 → operatør må generere ny refresh_token
  manuelt; auto-restart ville gått i evig auth-failure-loop (regresjon
  som vi så på scalp_edge i sub-fase 12.9-trigger).
- EnvironmentFile peker på ~/.bedrock/secrets.env slik at D2 refresh-
  token-persistering plukkes opp på neste start uten manuell handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

UNIT_PATH = Path("systemd/bedrock-bot.service")


@pytest.fixture(scope="module")
def unit_text() -> str:
    assert UNIT_PATH.exists(), f"mangler: {UNIT_PATH.resolve()}"
    return UNIT_PATH.read_text(encoding="utf-8")


def test_unit_has_unit_section(unit_text: str) -> None:
    assert "[Unit]" in unit_text
    assert "[Service]" in unit_text
    assert "[Install]" in unit_text


def test_unit_starts_after_network(unit_text: str) -> None:
    """Bot må vente på network-online før første poll. Bevisst ikke koblet
    mot bedrock-server.service: bot er user-unit, server er system-unit, og
    user-units kan ikke ``Requires=``/``After=`` system-units. Bot's egen
    fetch-fail-eskalering (safety.py) håndterer midlertidig server-bortfall.
    Se kommentar i unit-fila for full begrunnelse."""
    assert "After=" in unit_text
    after_line = next(line for line in unit_text.splitlines() if line.startswith("After="))
    assert "network-online.target" in after_line


def test_unit_environment_file_points_to_secrets_env(unit_text: str) -> None:
    """Refresh-token-persistering (D2) skriver til denne fila — service må
    laste den ved oppstart slik at oppdaterte tokens plukkes opp."""
    assert "EnvironmentFile=/home/pc/.bedrock/secrets.env" in unit_text


def test_unit_exec_start_uses_demo_mode(unit_text: str) -> None:
    """Cutover-perioden (12.9) er demo-only per § 21.7 stop-criterion."""
    exec_line = next(line for line in unit_text.splitlines() if line.startswith("ExecStart="))
    assert "/home/pc/bedrock/.venv/bin/python" in exec_line
    assert "-m bedrock.bot" in exec_line
    assert "--demo" in exec_line
    assert "--live" not in exec_line


def test_unit_restart_policy_excludes_fatal_codes(unit_text: str) -> None:
    """Exit 78 (FATAL — refresh-token-flyt ga opp) og 79 (reconnect-budsjett
    oppbrukt) skal ikke trigge auto-restart. Operatør må intervenere."""
    assert "Restart=on-failure" in unit_text
    line = next(
        line for line in unit_text.splitlines() if line.startswith("RestartPreventExitStatus=")
    )
    codes = line.split("=", 1)[1].split()
    assert "78" in codes
    assert "79" in codes


def test_unit_logs_to_journal(unit_text: str) -> None:
    """Strukturert logging via journald — gjør `journalctl --user -u
    bedrock-bot` til primær debug-kanal under demo-test (§ 21.7)."""
    assert "StandardOutput=journal" in unit_text
    assert "StandardError=journal" in unit_text


def test_unit_install_target(unit_text: str) -> None:
    assert "WantedBy=default.target" in unit_text
