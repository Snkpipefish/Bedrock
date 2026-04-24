"""Tester for `bedrock.config.secrets`."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bedrock.config.secrets import (
    SecretNotFoundError,
    get_secret,
    load_secrets,
    require_secret,
)


@pytest.fixture
def secrets_file(tmp_path: Path) -> Path:
    """Lager en secrets-fil med noen KEY=VALUE-linjer + kommentar."""
    path = tmp_path / "secrets.env"
    path.write_text(
        "# Bedrock secrets — do not commit\n"
        "FRED_API_KEY=abc123def456\n"
        "\n"
        "SCALP_API_KEY=xyz789\n"
        "# kommentar midt i filen\n"
        "EMPTY_LINE_OK=value_after_blank\n"
    )
    return path


@pytest.fixture(autouse=True)
def _clean_env_keys():
    """Fjern test-relaterte env-vars mellom tester."""
    keys = ("FRED_API_KEY", "SCALP_API_KEY", "MISSING_KEY", "EMPTY_LINE_OK", "TEST_ONLY")
    saved = {k: os.environ.pop(k, None) for k in keys}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


# ---------------------------------------------------------------------------
# load_secrets
# ---------------------------------------------------------------------------


def test_load_secrets_parses_key_value_pairs(secrets_file: Path) -> None:
    secrets = load_secrets(secrets_file)
    assert secrets["FRED_API_KEY"] == "abc123def456"
    assert secrets["SCALP_API_KEY"] == "xyz789"
    assert secrets["EMPTY_LINE_OK"] == "value_after_blank"


def test_load_secrets_ignores_comments(secrets_file: Path) -> None:
    secrets = load_secrets(secrets_file)
    assert "#" not in str(secrets.keys())


def test_load_secrets_nonexistent_file_returns_empty_dict(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.env"
    assert load_secrets(missing) == {}


# ---------------------------------------------------------------------------
# get_secret
# ---------------------------------------------------------------------------


def test_get_secret_from_file(secrets_file: Path) -> None:
    assert get_secret("FRED_API_KEY", path=secrets_file) == "abc123def456"


def test_get_secret_missing_returns_none(secrets_file: Path) -> None:
    assert get_secret("NEVER_DEFINED", path=secrets_file) is None


def test_get_secret_default_when_missing(secrets_file: Path) -> None:
    assert get_secret("NEVER_DEFINED", path=secrets_file, default="fallback") == "fallback"


def test_env_var_overrides_secrets_file(secrets_file: Path) -> None:
    os.environ["FRED_API_KEY"] = "from_env"
    assert get_secret("FRED_API_KEY", path=secrets_file) == "from_env"


def test_env_var_used_when_file_missing_key(secrets_file: Path) -> None:
    os.environ["TEST_ONLY"] = "env_value"
    assert get_secret("TEST_ONLY", path=secrets_file) == "env_value"


def test_env_var_used_when_file_not_exists(tmp_path: Path) -> None:
    missing = tmp_path / "no_file.env"
    os.environ["TEST_ONLY"] = "env_value"
    assert get_secret("TEST_ONLY", path=missing) == "env_value"


# ---------------------------------------------------------------------------
# require_secret
# ---------------------------------------------------------------------------


def test_require_secret_returns_value(secrets_file: Path) -> None:
    assert require_secret("FRED_API_KEY", path=secrets_file) == "abc123def456"


def test_require_secret_missing_raises(secrets_file: Path) -> None:
    with pytest.raises(SecretNotFoundError, match="MISSING_KEY"):
        require_secret("MISSING_KEY", path=secrets_file)


def test_require_secret_error_message_mentions_file_path(tmp_path: Path) -> None:
    missing = tmp_path / "no_file.env"
    with pytest.raises(SecretNotFoundError, match=str(missing)):
        require_secret("ANYKEY", path=missing)


# ---------------------------------------------------------------------------
# Default path
# ---------------------------------------------------------------------------


def test_default_path_expands_tilde() -> None:
    """DEFAULT_SECRETS_PATH skal være absolutt (ingen tilde)."""
    from bedrock.config.secrets import DEFAULT_SECRETS_PATH

    assert "~" not in str(DEFAULT_SECRETS_PATH)
    assert DEFAULT_SECRETS_PATH.is_absolute()


def test_load_secrets_default_path_used_when_none(tmp_path: Path) -> None:
    """Kalles uten path-arg skal bruke DEFAULT_SECRETS_PATH."""
    fake_default = tmp_path / "secrets.env"
    fake_default.write_text("DEFAULT_PATH_TEST=worked\n")

    with patch("bedrock.config.secrets.DEFAULT_SECRETS_PATH", fake_default):
        secrets = load_secrets()
    assert secrets.get("DEFAULT_PATH_TEST") == "worked"
