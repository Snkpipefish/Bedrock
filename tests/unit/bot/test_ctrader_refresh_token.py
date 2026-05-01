"""Tester for OAuth-refresh-flyten i `bot.ctrader_client` (sub-fase 12.9 D2).

Verifiserer:
- `refresh_ctrader_access_token` HTTP-respons-håndtering (200 / 4xx / 5xx /
  nettverk / parse-feil / mangler refresh_token).
- `_on_error_res` ved auth-fatal-kode triggrer refresh når refresh_token
  finnes, og fall-through til `_fatal_exit(78)` når den mangler eller
  refresh feiler.
- `_refresh_attempted`-vakten hindrer dobbel-retry i samme prosess.
- Persisterte tokens går via `update_secrets_env_var`, ikke direkte
  fil-skriv (caller-ansvar er begrenset til navnet).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from bedrock.bot.config import ReconnectConfig, StartupOnlyConfig
from bedrock.bot.ctrader_client import (
    CTRADER_TOKEN_ENDPOINT,
    CtraderCallbacks,
    CtraderClient,
    CtraderCredentials,
    RefreshTokenError,
    refresh_ctrader_access_token,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def creds_with_refresh() -> CtraderCredentials:
    return CtraderCredentials(
        client_id="cid",
        client_secret="csecret",
        access_token="old_access",
        account_id=42,
        refresh_token="old_refresh",
    )


@pytest.fixture
def creds_no_refresh() -> CtraderCredentials:
    return CtraderCredentials(
        client_id="cid",
        client_secret="csecret",
        access_token="old_access",
        account_id=42,
        refresh_token=None,
    )


@pytest.fixture
def startup_cfg() -> StartupOnlyConfig:
    return StartupOnlyConfig(reconnect=ReconnectConfig(max_in_window=5, window_sec=600))


def _client(creds: CtraderCredentials, startup_cfg: StartupOnlyConfig) -> CtraderClient:
    return CtraderClient(
        credentials=creds,
        demo=True,
        startup_config=startup_cfg,
        callbacks=CtraderCallbacks(),
    )


def _ok_response(access: str = "new_access", refresh: str = "new_refresh") -> MagicMock:
    resp = MagicMock(spec=["status_code", "json", "text"])
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": 2592000,
        "token_type": "bearer",
    }
    resp.text = "ok"
    return resp


# ─────────────────────────────────────────────────────────────
# refresh_ctrader_access_token — modul-level helper
# ─────────────────────────────────────────────────────────────


def test_refresh_token_posts_correct_payload(creds_with_refresh: CtraderCredentials) -> None:
    with patch("bedrock.bot.ctrader_client.requests.post") as post:
        post.return_value = _ok_response()
        body = refresh_ctrader_access_token(creds_with_refresh)

    assert body["access_token"] == "new_access"
    assert body["refresh_token"] == "new_refresh"
    args, kwargs = post.call_args
    assert args[0] == CTRADER_TOKEN_ENDPOINT
    assert kwargs["data"] == {
        "grant_type": "refresh_token",
        "refresh_token": "old_refresh",
        "client_id": "cid",
        "client_secret": "csecret",
    }
    assert kwargs["timeout"] > 0


def test_refresh_token_4xx_raises(creds_with_refresh: CtraderCredentials) -> None:
    resp = MagicMock(spec=["status_code", "json", "text"])
    resp.status_code = 401
    resp.text = "invalid_grant"
    with patch("bedrock.bot.ctrader_client.requests.post", return_value=resp):
        with pytest.raises(RefreshTokenError) as exc:
            refresh_ctrader_access_token(creds_with_refresh)
    assert exc.value.status_code == 401
    assert "invalid_grant" in exc.value.body


def test_refresh_token_5xx_raises(creds_with_refresh: CtraderCredentials) -> None:
    resp = MagicMock(spec=["status_code", "json", "text"])
    resp.status_code = 503
    resp.text = "service unavailable"
    with patch("bedrock.bot.ctrader_client.requests.post", return_value=resp):
        with pytest.raises(RefreshTokenError) as exc:
            refresh_ctrader_access_token(creds_with_refresh)
    assert exc.value.status_code == 503


def test_refresh_token_network_error_raises(creds_with_refresh: CtraderCredentials) -> None:
    with patch(
        "bedrock.bot.ctrader_client.requests.post",
        side_effect=requests.ConnectionError("boom"),
    ):
        with pytest.raises(RefreshTokenError) as exc:
            refresh_ctrader_access_token(creds_with_refresh)
    assert exc.value.status_code is None
    assert "boom" in exc.value.body


def test_refresh_token_invalid_json_raises(creds_with_refresh: CtraderCredentials) -> None:
    resp = MagicMock(spec=["status_code", "json", "text"])
    resp.status_code = 200
    resp.json.side_effect = ValueError("not json")
    resp.text = "<html>oops</html>"
    with patch("bedrock.bot.ctrader_client.requests.post", return_value=resp):
        with pytest.raises(RefreshTokenError) as exc:
            refresh_ctrader_access_token(creds_with_refresh)
    assert exc.value.status_code == 200


def test_refresh_token_missing_access_field_raises(creds_with_refresh: CtraderCredentials) -> None:
    resp = MagicMock(spec=["status_code", "json", "text"])
    resp.status_code = 200
    resp.json.return_value = {"expires_in": 2592000}  # mangler access_token
    resp.text = ""
    with patch("bedrock.bot.ctrader_client.requests.post", return_value=resp):
        with pytest.raises(RefreshTokenError):
            refresh_ctrader_access_token(creds_with_refresh)


def test_refresh_token_no_refresh_token_raises(creds_no_refresh: CtraderCredentials) -> None:
    """Skal ikke engang HTTP-kalle hvis creds.refresh_token er None."""
    with patch("bedrock.bot.ctrader_client.requests.post") as post:
        with pytest.raises(RefreshTokenError):
            refresh_ctrader_access_token(creds_no_refresh)
    post.assert_not_called()


# ─────────────────────────────────────────────────────────────
# _on_error_res integrasjon — refresh + retry-vakt
# ─────────────────────────────────────────────────────────────


def test_on_error_res_no_refresh_token_falls_back_to_fatal(
    creds_no_refresh: CtraderCredentials,
    startup_cfg: StartupOnlyConfig,
) -> None:
    """Back-compat: uten refresh_token → direkte _fatal_exit(78)."""
    c = _client(creds_no_refresh, startup_cfg)
    err = MagicMock()
    err.errorCode = "CH_ACCESS_TOKEN_INVALID"
    with (
        patch("bedrock.bot.ctrader_client.requests.post") as post,
        patch.object(c, "_fatal_exit") as fatal,
        patch.object(c, "_authenticate_application") as auth,
    ):
        c._on_error_res(err)
    fatal.assert_called_once_with(78)
    auth.assert_not_called()
    post.assert_not_called()


def test_on_error_res_refresh_success_skips_fatal_and_reauths(
    creds_with_refresh: CtraderCredentials,
    startup_cfg: StartupOnlyConfig,
) -> None:
    c = _client(creds_with_refresh, startup_cfg)
    err = MagicMock()
    err.errorCode = "ACCESS_TOKEN_EXPIRED"
    with (
        patch("bedrock.bot.ctrader_client.requests.post", return_value=_ok_response()),
        patch("bedrock.bot.ctrader_client.update_secrets_env_var") as upd,
        patch.object(c, "_fatal_exit") as fatal,
        patch.object(c, "_authenticate_application") as auth,
    ):
        c._on_error_res(err)

    fatal.assert_not_called()
    auth.assert_called_once()
    # access + refresh begge persistert
    keys = [call.args[0] for call in upd.call_args_list]
    assert "CTRADER_ACCESS_TOKEN" in keys
    assert "CTRADER_REFRESH_TOKEN" in keys
    # In-memory creds er oppdatert
    assert c._creds.access_token == "new_access"
    assert c._creds.refresh_token == "new_refresh"
    assert c._refresh_attempted is True


def test_on_error_res_refresh_http_failure_falls_back_to_fatal(
    creds_with_refresh: CtraderCredentials,
    startup_cfg: StartupOnlyConfig,
) -> None:
    c = _client(creds_with_refresh, startup_cfg)
    err = MagicMock()
    err.errorCode = "ACCESS_TOKEN_EXPIRED"
    bad_resp = MagicMock(spec=["status_code", "json", "text"])
    bad_resp.status_code = 401
    bad_resp.text = "invalid_grant"
    with (
        patch("bedrock.bot.ctrader_client.requests.post", return_value=bad_resp),
        patch("bedrock.bot.ctrader_client.update_secrets_env_var") as upd,
        patch.object(c, "_fatal_exit") as fatal,
        patch.object(c, "_authenticate_application") as auth,
    ):
        c._on_error_res(err)

    fatal.assert_called_once_with(78)
    auth.assert_not_called()
    upd.assert_not_called()
    assert c._refresh_attempted is True  # vakten settes også ved feil


def test_on_error_res_double_call_does_not_double_refresh(
    creds_with_refresh: CtraderCredentials,
    startup_cfg: StartupOnlyConfig,
) -> None:
    """Andre auth-fatal i samme prosess → direkte fatal (vakt aktiv)."""
    c = _client(creds_with_refresh, startup_cfg)
    err = MagicMock()
    err.errorCode = "CH_ACCESS_TOKEN_INVALID"

    # Første kall: refresh OK, _fatal_exit ikke kalt
    with (
        patch("bedrock.bot.ctrader_client.requests.post", return_value=_ok_response()),
        patch("bedrock.bot.ctrader_client.update_secrets_env_var"),
        patch.object(c, "_fatal_exit") as fatal1,
        patch.object(c, "_authenticate_application"),
    ):
        c._on_error_res(err)
    fatal1.assert_not_called()

    # Andre kall: skal ikke refreshe igjen → fatal
    with (
        patch("bedrock.bot.ctrader_client.requests.post") as post2,
        patch.object(c, "_fatal_exit") as fatal2,
        patch.object(c, "_authenticate_application") as auth2,
    ):
        c._on_error_res(err)
    fatal2.assert_called_once_with(78)
    post2.assert_not_called()
    auth2.assert_not_called()


def test_on_error_res_persist_failure_falls_back_to_fatal(
    creds_with_refresh: CtraderCredentials,
    startup_cfg: StartupOnlyConfig,
) -> None:
    """Hvis update_secrets_env_var raiser → vi exiter FATAL i stedet for
    å kjøre videre med en ikke-persistert token."""
    c = _client(creds_with_refresh, startup_cfg)
    err = MagicMock()
    err.errorCode = "OA_AUTH_TOKEN_EXPIRED"
    with (
        patch("bedrock.bot.ctrader_client.requests.post", return_value=_ok_response()),
        patch(
            "bedrock.bot.ctrader_client.update_secrets_env_var",
            side_effect=OSError("disk full"),
        ),
        patch.object(c, "_fatal_exit") as fatal,
        patch.object(c, "_authenticate_application") as auth,
    ):
        c._on_error_res(err)

    fatal.assert_called_once_with(78)
    auth.assert_not_called()


def test_on_error_res_non_fatal_code_does_not_touch_refresh(
    creds_with_refresh: CtraderCredentials,
    startup_cfg: StartupOnlyConfig,
) -> None:
    """Ikke-auth-feil (f.eks. transient ordrefeil) skal ikke utløse refresh."""
    on_err = MagicMock()
    cb = CtraderCallbacks(on_error_res=on_err)
    c = CtraderClient(
        credentials=creds_with_refresh, demo=True, startup_config=startup_cfg, callbacks=cb
    )
    err = MagicMock()
    err.errorCode = "SYMBOL_NOT_FOUND"
    with (
        patch("bedrock.bot.ctrader_client.requests.post") as post,
        patch.object(c, "_fatal_exit") as fatal,
    ):
        c._on_error_res(err)
    post.assert_not_called()
    fatal.assert_not_called()
    on_err.assert_called_once_with(err)
    assert c._refresh_attempted is False


# ─────────────────────────────────────────────────────────────
# CtraderCredentials + load_credentials_from_env (refresh-token-felt)
# ─────────────────────────────────────────────────────────────


def test_credentials_default_refresh_token_is_none() -> None:
    creds = CtraderCredentials(client_id="cid", client_secret="cs", access_token="t", account_id=1)
    assert creds.refresh_token is None


def test_load_credentials_picks_up_refresh_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from bedrock.bot.ctrader_client import load_credentials_from_env

    monkeypatch.setenv("CTRADER_CLIENT_ID", "cid")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "cs")
    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("CTRADER_REFRESH_TOKEN", "refr")
    monkeypatch.setenv("CTRADER_ACCOUNT_ID", "777")
    creds = load_credentials_from_env()
    assert creds.refresh_token == "refr"


def test_load_credentials_refresh_token_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mangler CTRADER_REFRESH_TOKEN er IKKE en hard feil (back-compat)."""
    from bedrock.bot.ctrader_client import load_credentials_from_env

    monkeypatch.setenv("CTRADER_CLIENT_ID", "cid")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "cs")
    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "tok")
    monkeypatch.delenv("CTRADER_REFRESH_TOKEN", raising=False)
    monkeypatch.setenv("CTRADER_ACCOUNT_ID", "777")
    creds = load_credentials_from_env()
    assert creds.refresh_token is None


def test_refresh_token_error_attrs() -> None:
    err = RefreshTokenError(503, "down")
    assert err.status_code == 503
    assert err.body == "down"
    assert "503" in str(err)
