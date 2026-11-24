"""Felles fixtures for bot-enhetstester."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _empty_secrets_on_disk() -> Iterator[MagicMock]:
    """Hindrer at bot-testene leser utviklerens ekte `~/.bedrock/secrets.env`.

    `CtraderClient` leser tokens fra disk ved auth-fatal-feil. Default her:
    ingen tokens på disk → disk-reload er no-op. Disk-reload-testene setter
    `return_value` / `side_effect` selv.
    """
    with patch("bedrock.bot.ctrader_client.load_secrets", return_value={}) as m:
        yield m
