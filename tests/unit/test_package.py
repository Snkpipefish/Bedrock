"""Triviell smoke-test — verifiserer at pakken kan importeres.

Denne testen eksisterer primært for å gi CI noe å kjøre grønt på i Fase 0.
Erstattes av ekte tester i Fase 1 (Engine, drivers).
"""

import bedrock


def test_package_has_version() -> None:
    assert bedrock.__version__ == "0.0.1"


def test_package_version_is_semver_like() -> None:
    parts = bedrock.__version__.split(".")
    assert len(parts) == 3
    for part in parts:
        assert part.isdigit()
