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
    update_secrets_env_var,
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


# ---------------------------------------------------------------------------
# update_secrets_env_var (sub-fase 12.9 D2)
# ---------------------------------------------------------------------------


def test_update_creates_file_when_missing(tmp_path: Path) -> None:
    target = tmp_path / "new.env"
    update_secrets_env_var("FOO", "bar", path=target)
    assert target.read_text() == "FOO=bar\n"
    # 600 i lavest tre bitter (eier=rw, andre=ingen)
    assert (target.stat().st_mode & 0o777) == 0o600


def test_update_replaces_existing_key(tmp_path: Path) -> None:
    target = tmp_path / "secrets.env"
    target.write_text("FOO=old\nBAR=keep\n")
    update_secrets_env_var("FOO", "new", path=target)
    text = target.read_text()
    assert "FOO=new\n" in text
    assert "FOO=old" not in text
    assert "BAR=keep\n" in text


def test_update_appends_when_key_missing(tmp_path: Path) -> None:
    target = tmp_path / "secrets.env"
    target.write_text("BAR=keep\n")
    update_secrets_env_var("FOO", "bar", path=target)
    text = target.read_text()
    assert text.endswith("FOO=bar\n")
    assert "BAR=keep\n" in text


def test_update_does_not_match_commented_key(tmp_path: Path) -> None:
    target = tmp_path / "secrets.env"
    target.write_text("# FOO=commented_out\nFOO=real\n")
    update_secrets_env_var("FOO", "new", path=target)
    text = target.read_text()
    assert "# FOO=commented_out" in text
    assert "FOO=new" in text
    assert "FOO=real" not in text


def test_update_does_not_match_prefix_key(tmp_path: Path) -> None:
    """`FOO_X=...` skal ikke bli matchet når vi oppdaterer `FOO`."""
    target = tmp_path / "secrets.env"
    target.write_text("FOO_X=keep\nFOO=old\n")
    update_secrets_env_var("FOO", "new", path=target)
    text = target.read_text()
    assert "FOO_X=keep" in text
    assert "FOO=new" in text


def test_update_preserves_permissions_on_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "secrets.env"
    target.write_text("FOO=old\n")
    os.chmod(target, 0o600)
    update_secrets_env_var("FOO", "new", path=target)
    assert (target.stat().st_mode & 0o777) == 0o600


def test_update_rejects_newline_in_value(tmp_path: Path) -> None:
    target = tmp_path / "secrets.env"
    target.write_text("")
    with pytest.raises(ValueError, match="newline"):
        update_secrets_env_var("FOO", "line1\nline2", path=target)


def test_update_rejects_invalid_key(tmp_path: Path) -> None:
    target = tmp_path / "secrets.env"
    with pytest.raises(ValueError):
        update_secrets_env_var("BAD=KEY", "v", path=target)
    with pytest.raises(ValueError):
        update_secrets_env_var("", "v", path=target)


def test_update_atomic_no_partial_file_on_chmod_failure(tmp_path: Path) -> None:
    """Hvis chmod feiler skal target-fila være urørt (atomic-replace ikke
    kjørt). Verifiserer at vi ikke etterlater half-skrevet fil."""
    target = tmp_path / "secrets.env"
    target.write_text("FOO=old\n")
    with patch("bedrock.config.secrets.os.chmod", side_effect=OSError("perm denied")):
        with pytest.raises(OSError):
            update_secrets_env_var("FOO", "new", path=target)
    # Original innhold uendret
    assert target.read_text() == "FOO=old\n"
    # Ingen .secrets-* tempfile lekket i mappen
    leftovers = list(tmp_path.glob(".secrets-*"))
    assert leftovers == []


def test_update_round_trip_with_load_secrets(tmp_path: Path) -> None:
    target = tmp_path / "secrets.env"
    target.write_text("FOO=v1\nBAR=keep\n")
    update_secrets_env_var("FOO", "v2", path=target)
    update_secrets_env_var("BAZ", "v3", path=target)
    secrets = load_secrets(target)
    assert secrets["FOO"] == "v2"
    assert secrets["BAR"] == "keep"
    assert secrets["BAZ"] == "v3"


def test_update_default_path_used_when_none(tmp_path: Path) -> None:
    fake_default = tmp_path / "secrets.env"
    fake_default.write_text("FOO=old\n")
    with patch("bedrock.config.secrets.DEFAULT_SECRETS_PATH", fake_default):
        update_secrets_env_var("FOO", "new")
    assert "FOO=new" in fake_default.read_text()
