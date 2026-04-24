"""Signal-server HTTP-lag + daglig batch-git-commit av trade-log.

Portert fra `~/scalp_edge/trading_bot.py` session 42 per migrasjons-
plan (`docs/migration/bot_refactor.md § 3.7 + 8 punkt 3`). Null
logikk-endring utover:

- `SIGNAL_URL` leses fra `StartupOnlyConfig.signal_url` i stedet for
  modul-global env-var
- `_git_push_log` (no-op i gammel bot siden cot-explorer tok over
  push) erstattes av `commit_daily_trade_log()` som kalles fra
  `SafetyMonitor`s `on_rollover`-hook ved midnatt UTC.
  `.githooks/post-commit` pusher resultatet (bruker bekreftet
  session 39)
- Retry-logikk er hand-rolled matching scalp_edge-atferd (0/1/3 s
  backoff, maks 3 forsøk)
- `adaptive_poll_interval()` er trukket ut som ren funksjon for
  test-isolering; polling-loopen selv wirer inn Twisted reactor

Ansvaret:
- HTTP GET /signals + parse + schema-versjon-varsel
- HTTP GET /kill → liste av signal-IDs som skal stoppes
- HTTP POST /push-prices
- Adaptiv polling-intervall (SCALP aktiv → kort, ellers lang)
- Git-commit av trade-log en gang per dag

Ikke-ansvar:
- Selve polling-løkken med `reactor.callLater` — implementeres i
  `bot/__main__.py` eller egen `polling.py` i session 45 når Twisted-
  wiring er relevant. Ren HTTP og interval-beregning er her
- Hva som faktisk skrives til trade-log — `bot/entry.py` og
  `bot/exit.py` eier log-formatet
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

import requests

from bedrock.bot.config import PollingConfig, StartupOnlyConfig
from bedrock.bot.instruments import INSTRUMENT_TO_PRICE_KEY
from bedrock.bot.safety import SafetyMonitor

log = logging.getLogger("bedrock.bot.comms")

# Signal-schema-versjoner som bot støtter. Utenom-versjoner gir én warning
# per unik versjon (ikke hard block) slik at forward-kompatible endringer
# ikke stopper boten.
SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1.0", "2.0", "2.1"})

# Retry-backoff: første forsøk umiddelbart, så 1s, så 3s
_RETRY_DELAYS: tuple[int, ...] = (0, 1, 3)

# Default-sti for trade-log (entry/exit skriver hit i session 43-44)
DEFAULT_TRADE_LOG_PATH = Path.home() / "bedrock" / "data" / "bot" / "trade_log.jsonl"


def _noop(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover
    pass


# ─────────────────────────────────────────────────────────────
# Rene funksjoner (test-isolerte)
# ─────────────────────────────────────────────────────────────


def adaptive_poll_interval(
    signals_data: Optional[dict[str, Any]], cfg: PollingConfig
) -> int:
    """Returner kort intervall hvis SCALP-signaler er aktive, ellers default.

    Matcher scalp_edge:`_fetch_signals_loop` semantikk — sjekker
    `signals[*].horizon == "SCALP"` og `status == "watchlist"`.
    """
    if not signals_data:
        return cfg.default_seconds
    for sig in signals_data.get("signals", []):
        if sig.get("horizon") == "SCALP" and sig.get("status") == "watchlist":
            return cfg.scalp_active_seconds
    return cfg.default_seconds


def assemble_prices_from_state(
    symbol_map: dict[str, int],
    price_feed_sids: dict[str, int],
    last_bid: dict[int, float],
) -> dict[str, dict[str, float]]:
    """Bygg `{price_key: {"value": bid}}`-dict fra CtraderClient-state.

    Dekker både trading-instrumenter (via `INSTRUMENT_TO_PRICE_KEY`) og
    rene pris-feed-symboler. Kun instrumenter med siste-bid inkluderes.
    """
    prices: dict[str, dict[str, float]] = {}
    for instr_name, price_key in INSTRUMENT_TO_PRICE_KEY.items():
        sid = symbol_map.get(instr_name)
        if sid is not None and sid in last_bid:
            prices[price_key] = {"value": round(last_bid[sid], 5)}
    for price_key, sid in price_feed_sids.items():
        if sid in last_bid:
            prices[price_key] = {"value": round(last_bid[sid], 5)}
    return prices


# ─────────────────────────────────────────────────────────────
# Daglig batch-commit av trade-log
# ─────────────────────────────────────────────────────────────


def commit_daily_trade_log(
    log_path: Path,
    log_date: date,
    repo_root: Path,
) -> bool:
    """Git-add + git-commit av trade-log-fila.

    Kalles fra `SafetyMonitor.on_rollover`-hook ved midnatt UTC med
    gårsdagens dato. `.githooks/post-commit` håndterer push.

    Retur:
        True hvis commit lyktes (eller ingen endringer å committe)
        False ved feil — logges som warning, ikke fatal (daglig tapsreset
        må fortsette selv om git-commit feiler)

    Feil-toleranse:
        - Hvis log-fila ikke finnes → returner True (ingen trades å logge)
        - Hvis git-add feiler → log warning, returner False
        - Hvis git-commit returnerer ikke-null fordi ingen diff → True
        - Hvis repo-root ikke er git-repo → log warning, returner False
    """
    if not log_path.exists():
        log.info("[TRADE-LOG] Ingen log-fil å committe (%s)", log_path)
        return True

    if not (repo_root / ".git").exists():
        log.warning("[TRADE-LOG] %s er ikke et git-repo — hopper over commit", repo_root)
        return False

    # Rel-path for git-add (må være innenfor repo)
    try:
        rel_path = log_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        log.warning(
            "[TRADE-LOG] %s er utenfor repo %s — hopper over commit",
            log_path,
            repo_root,
        )
        return False

    # git add
    add_result = subprocess.run(
        ["git", "add", "--", str(rel_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if add_result.returncode != 0:
        log.warning(
            "[TRADE-LOG] git add feilet: %s", add_result.stderr.strip()
        )
        return False

    # git commit — kan returnere 1 hvis ingen endringer, det er OK
    commit_msg = f"log: bot trades {log_date.isoformat()}"
    commit_result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if commit_result.returncode == 0:
        log.info("[TRADE-LOG] Committet trade-log for %s", log_date.isoformat())
        return True

    # Returnkode 1 + "nothing to commit" = ingen endring, success
    out = (commit_result.stdout + commit_result.stderr).lower()
    if "nothing to commit" in out or "no changes added" in out:
        log.info("[TRADE-LOG] Ingen endringer å committe for %s", log_date.isoformat())
        return True

    log.warning(
        "[TRADE-LOG] git commit feilet (rc=%d): %s",
        commit_result.returncode,
        commit_result.stderr.strip() or commit_result.stdout.strip(),
    )
    return False


# ─────────────────────────────────────────────────────────────
# SignalComms — HTTP-klient mot signal-server
# ─────────────────────────────────────────────────────────────


@dataclass
class FetchResult:
    """Resultat fra fetch_signals — makes tester enklere enn tuple-return."""

    signals_data: Optional[dict[str, Any]]
    kill_ids: list[str]


class SignalComms:
    """HTTP-grensesnitt mot Bedrock signal-server (port 5100).

    Eier ikke polling-loopen — caller i `bot/__main__.py` wirer
    `reactor.callLater` rundt `fetch_once()`. Dette holder
    SignalComms testbar uten Twisted.
    """

    def __init__(
        self,
        *,
        startup_cfg: StartupOnlyConfig,
        api_key: str,
        safety: SafetyMonitor,
        on_signals: Callable[[dict[str, Any]], None] = _noop,
        on_kill_ids: Callable[[list[str]], None] = _noop,
        session: Optional[requests.Session] = None,
    ) -> None:
        self._url = startup_cfg.signal_url.rstrip("/")
        self._api_key = api_key
        self._safety = safety
        self._on_signals = on_signals
        self._on_kill_ids = on_kill_ids
        self._session = session or requests.Session()
        self._schema_warned: set[str] = set()
        # Siste mottatte signal-data — brukes av caller til å beregne
        # adaptiv poll-intervall
        self.latest_signals: Optional[dict[str, Any]] = None

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key} if self._api_key else {}

    def _fetch_with_retry(
        self, path: str, *, timeout: int
    ) -> Optional[requests.Response]:
        """GET med 3-trinns retry (0/1/3 s backoff). Retry kun på 5xx og
        nettverksfeil; 4xx returneres umiddelbart. Returnerer None hvis
        siste forsøk kastet eksepsjon.

        `time.sleep` slås opp per kall slik at tester kan mocke det via
        `patch("bedrock.bot.comms.time.sleep")`.
        """
        url = f"{self._url}{path}"
        headers = self._headers()
        last_exc: Optional[Exception] = None
        for i, d in enumerate(_RETRY_DELAYS):
            if d:
                time.sleep(d)
            try:
                r = self._session.get(url, timeout=timeout, headers=headers)
                if r.status_code == 200:
                    return r
                if 500 <= r.status_code < 600 and i < len(_RETRY_DELAYS) - 1:
                    log.debug("[FETCH] %s HTTP %d, retry %d", url, r.status_code, i + 1)
                    continue
                return r
            except requests.exceptions.RequestException as e:
                last_exc = e
                if i < len(_RETRY_DELAYS) - 1:
                    log.debug("[FETCH] %s feilet (%s), retry %d", url, e, i + 1)
                    continue
                # Siste forsøk feilet
                raise
        if last_exc:
            raise last_exc
        return None  # pragma: no cover (unreachable)

    # ─────────────────────────────────────────────────────────
    # Public HTTP-operasjoner
    # ─────────────────────────────────────────────────────────

    def fetch_signals(self) -> Optional[dict[str, Any]]:
        """Hent /signals. Oppdaterer safety-tellere + `latest_signals` +
        kaller `on_signals`-callback med parsed dict. Returnerer dict
        eller None ved feil."""
        try:
            resp = self._fetch_with_retry("/signals", timeout=8)
        except requests.exceptions.RequestException as e:
            self._safety.record_fetch_failure(str(e))
            return None

        if resp is None or resp.status_code != 200:
            status = resp.status_code if resp is not None else "none"
            self._safety.record_fetch_failure(f"HTTP {status}")
            return None

        try:
            data = resp.json()
        except ValueError as e:
            self._safety.record_fetch_failure(f"JSON parse: {e}")
            return None

        # Schema-versjon-sjekk
        sv = data.get("schema_version")
        if sv and sv not in SUPPORTED_SCHEMA_VERSIONS and sv not in self._schema_warned:
            log.warning(
                "[SCHEMA] Mottok schema_version=%r — bot støtter %s. "
                "Felt kan mangle eller ha endret semantikk.",
                sv,
                sorted(SUPPORTED_SCHEMA_VERSIONS),
            )
            self._schema_warned.add(sv)

        self._safety.record_fetch_success()
        self.latest_signals = data
        try:
            self._on_signals(data)
        except Exception:
            log.exception("[CALLBACK] on_signals feilet")
        return data

    def fetch_kill_ids(self) -> list[str]:
        """Hent /kill. Kill-liste feil fryser IKKE bot (uavhengig av /signals)."""
        try:
            resp = self._fetch_with_retry("/kill", timeout=5)
        except requests.exceptions.RequestException as e:
            log.warning("[SERVER] /kill feilet etter retries: %s", e)
            return []

        if resp is None or resp.status_code != 200:
            return []

        try:
            data = resp.json()
        except ValueError:
            return []

        # Endpoint returnerer enten liste med IDs eller dict med "signal_ids"
        ids: list[str]
        if isinstance(data, list):
            ids = [str(x) for x in data]
        elif isinstance(data, dict):
            raw = data.get("signal_ids") or data.get("kills") or []
            ids = [str(x) for x in raw]
        else:
            ids = []

        if ids:
            try:
                self._on_kill_ids(ids)
            except Exception:
                log.exception("[CALLBACK] on_kill_ids feilet")
        return ids

    def push_prices(self, prices: dict[str, dict[str, float]]) -> bool:
        """POST /push-prices med assembled prices-dict. Returnerer True
        ved HTTP 2xx."""
        if not prices:
            log.warning("[PRISER] Ingen priser å pushe ennå.")
            return False
        try:
            resp = self._session.post(
                f"{self._url}/push-prices",
                headers={
                    **self._headers(),
                    "Content-Type": "application/json",
                },
                json={"prices": prices},
                timeout=5,
            )
            ok = 200 <= resp.status_code < 300
            log.info(
                "[PRISER] %d priser pushet → HTTP %d", len(prices), resp.status_code
            )
            return ok
        except Exception as exc:
            log.warning("[PRISER] Push feilet: %s", exc)
            return False

    def fetch_once(self) -> FetchResult:
        """Convenience: hent /signals + /kill i én runde. Brukes av
        polling-loopen i `bot/__main__.py`."""
        signals = self.fetch_signals()
        kill_ids = self.fetch_kill_ids()
        return FetchResult(signals_data=signals, kill_ids=kill_ids)
