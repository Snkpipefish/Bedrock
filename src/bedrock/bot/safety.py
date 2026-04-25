"""Safety-lag: daily-loss-state, kill-switch-flagg, fetch-fail-eskalering.

Portert fra `~/scalp_edge/trading_bot.py` session 42 per migrasjons-
plan (`docs/migration/bot_refactor.md § 3.6 + 8 punkt 3`). Null
logikk-endring utover:

- Daily-loss-state-fila flyttet fra `~/scalp_edge/daily_loss_state.json`
  til `~/bedrock/data/bot/daily_loss_state.json` (samme semantikk)
- `reset_daily_loss_if_new_day()` tar en `on_rollover`-callback som
  `bot/comms.py` wirer til daglig batch-git-commit av trade-log
  (session 39 bekreftet). Denne hooken er grunnen til at daglig-
  reset ikke er "internal" lenger — comms trenger signal om
  dag-rollover for commit-vinduet
- Fetch-fail-telling er kapslet i `SafetyMonitor` i stedet for felt
  spredt på bot-klassen

Ansvaret:
- Eie daily-loss-tall + persistere det atomisk til disk
- Rulle over ved ny UTC-dag og utløse callback
- Beregne daily-loss-limit (max(pct × balance, nok-gulv))
- Holde flagg: `server_frozen`, `bot_locked`, `bot_locked_until`
- Eskalerende fetch-fail-logging (info → warning → error hvert 10.)

Ikke-ansvar:
- Selve HTTP-fetch (bor i `bot/comms.py`)
- Trade-execution gate (entry leser `daily_loss_exceeded` før inngang)
- Kill-signal-fetch (comms henter liste; entry/exit setter
  `state.kill_switch` direkte — safety holder kun flagg per bot)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from bedrock.bot.config import DailyLossConfig

log = logging.getLogger("bedrock.bot.safety")


# ─────────────────────────────────────────────────────────────
# Default-sti for daily-loss persistens
# ─────────────────────────────────────────────────────────────

DEFAULT_DAILY_LOSS_STATE_PATH = Path.home() / "bedrock" / "data" / "bot" / "daily_loss_state.json"


# ─────────────────────────────────────────────────────────────
# Type-alias for dag-rollover-hook
# ─────────────────────────────────────────────────────────────

# Kalles med (forrige_dato, ny_dato) ved midnatt UTC. Typisk bruk:
# comms.py committer gårsdagens trade-log.
DayRolloverCallback = Callable[[date, date], None]


def _noop_rollover(_prev: date, _new: date) -> None:  # pragma: no cover
    pass


# ─────────────────────────────────────────────────────────────
# SafetyMonitor
# ─────────────────────────────────────────────────────────────


@dataclass
class _PersistedState:
    """Disk-representasjon av state."""

    date: date
    daily_loss: float

    def to_json(self) -> str:
        return json.dumps(
            {"date": self.date.isoformat(), "daily_loss": self.daily_loss},
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, text: str) -> _PersistedState:
        data = json.loads(text)
        return cls(
            date=date.fromisoformat(data["date"]),
            daily_loss=float(data.get("daily_loss", 0.0)),
        )


class SafetyMonitor:
    """Sentralisert sikkerhets-state for bot-prosessen.

    Én instans per bot-prosess. Ikke thread-safe for samtidige writes
    (Twisted reactor-tråden eier dette).
    """

    def __init__(
        self,
        *,
        state_path: Path | None = None,
        on_rollover: DayRolloverCallback | None = None,
    ) -> None:
        self._state_path = state_path or DEFAULT_DAILY_LOSS_STATE_PATH
        self._on_rollover = on_rollover or _noop_rollover

        # Daily-loss state (lastes fra disk ved oppstart)
        today = datetime.now(UTC).date()
        self._state = _PersistedState(date=today, daily_loss=0.0)
        self._load_state()

        # Flagg satt av andre lag
        self.server_frozen: bool = False
        self.bot_locked: bool = False
        self.bot_locked_until: datetime | None = None

        # Fetch-fail-eskalering
        self._fetch_fail_count: int = 0
        self._fetch_frozen_since: float | None = None

    # ─────────────────────────────────────────────────────────
    # Daily-loss state
    # ─────────────────────────────────────────────────────────

    @property
    def daily_loss(self) -> float:
        return self._state.daily_loss

    @property
    def daily_loss_date(self) -> date:
        return self._state.date

    def add_loss(self, amount: float) -> None:
        """Legg til et tap (positivt tall) til dagens akkumulasjon.

        Persisteres til disk umiddelbart slik at botrestart midt i en
        tapsdag ikke "glemmer" oppsamlet tap.
        """
        if amount < 0:
            log.warning("[SAFETY] add_loss fikk negativ verdi %s — ignoreres", amount)
            return
        self._state.daily_loss += amount
        self._save_state()

    def reset_daily_loss_if_new_day(self) -> bool:
        """Sjekk om dagens dato er forskjellig fra state-dato; resett hvis så.

        Returnerer True hvis det ble rollet over. Kaller da
        `on_rollover(prev_date, new_date)` BEFORE state resettes til 0,
        slik at callback kan bruke gårsdagens dato til commit-melding.
        """
        today = datetime.now(UTC).date()
        if today <= self._state.date:
            return False
        prev_date = self._state.date
        # Kall hook FØR state resettes — callback kan trenge gammel dato
        try:
            self._on_rollover(prev_date, today)
        except Exception:
            log.exception("[SAFETY] on_rollover-callback kastet — fortsetter reset")
        self._state = _PersistedState(date=today, daily_loss=0.0)
        self._save_state()
        log.info("[RESET] Daglig tap nullstilt for %s", today.isoformat())
        return True

    # ─────────────────────────────────────────────────────────
    # Daily-loss limit-beregning
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def daily_loss_limit(balance: float, cfg: DailyLossConfig) -> float:
        """max(pct × balance, nok-gulv). NOK-gulvet dominerer for små kontoer."""
        pct_limit = balance * (cfg.pct_of_balance / 100.0) if balance > 0 else 0
        return max(pct_limit, cfg.minimum_nok)

    def daily_loss_exceeded(self, balance: float, cfg: DailyLossConfig) -> bool:
        """Er dagens tap over limit-en?"""
        return self._state.daily_loss >= self.daily_loss_limit(balance, cfg)

    # ─────────────────────────────────────────────────────────
    # Fetch-fail-eskalering (kalles fra comms.py)
    # ─────────────────────────────────────────────────────────

    @property
    def fetch_fail_count(self) -> int:
        return self._fetch_fail_count

    @property
    def fetch_frozen_since(self) -> float | None:
        return self._fetch_frozen_since

    def record_fetch_success(self) -> None:
        """Kalles når signal-fetch lykkes. Logger gjenoppretting hvis vi
        har vært frosne, og resetter tellerne."""
        if self.server_frozen or self._fetch_fail_count > 0:
            frozen_for = time.time() - self._fetch_frozen_since if self._fetch_frozen_since else 0
            log.info(
                "[SERVER] Gjenopprettet kontakt — var frossen i %.0fs (%d feil).",
                frozen_for,
                self._fetch_fail_count,
            )
        self.server_frozen = False
        self._fetch_fail_count = 0
        self._fetch_frozen_since = None

    def record_fetch_failure(self, reason: str) -> None:
        """Eskalerende log basert på hvor lenge vi har vært frosne.

        - n <= 2:  INFO
        - 3 <= n < 10:  WARNING
        - n >= 10, n % 10 == 0:  ERROR hvert 10. forsøk (anti-spam)
        """
        self.server_frozen = True
        self._fetch_fail_count += 1
        if self._fetch_frozen_since is None:
            self._fetch_frozen_since = time.time()
        frozen_for = time.time() - self._fetch_frozen_since
        n = self._fetch_fail_count

        if n <= 2:
            log.info(
                "[SERVER] Signal-fetch feilet (%s) — forsøk #%d, fortsetter å polle.",
                reason,
                n,
            )
        elif n < 10:
            log.warning(
                "[SERVER] Signal-fetch feilet (%s) — %d strake feil, frossen i %.0fs.",
                reason,
                n,
                frozen_for,
            )
        else:
            if n % 10 == 0:
                log.error(
                    "[SERVER] Signal-fetch vedvarende feil (%s) — %d strake feil, "
                    "frossen i %.1f min. Sjekk signal_server og nettverk.",
                    reason,
                    n,
                    frozen_for / 60,
                )

    # ─────────────────────────────────────────────────────────
    # Intern persistens
    # ─────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        """Last state fra disk hvis den finnes og er fra samme dag."""
        if not self._state_path.exists():
            return
        try:
            text = self._state_path.read_text(encoding="utf-8")
            saved = _PersistedState.from_json(text)
        except Exception as e:
            log.warning("[SAFETY] Kunne ikke laste daily_loss_state: %s", e)
            return

        today = datetime.now(UTC).date()
        if saved.date == today:
            self._state = saved
            log.info(
                "[SAFETY] Lastet daglig tap fra disk: %.0f (dato %s)",
                saved.daily_loss,
                saved.date.isoformat(),
            )
        else:
            # State er fra tidligere dag — ignorer, men trigger ikke
            # rollover-callback ennå (det gjøres ved første
            # reset_daily_loss_if_new_day-kall i normal flyt).
            log.info("[SAFETY] Daglig-tap-state er fra %s — ignorerer.", saved.date.isoformat())

    def _save_state(self) -> None:
        """Atomic write: skriv til temp + os.replace."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                prefix="daily_loss_",
                suffix=".json",
                dir=self._state_path.parent,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(self._state.to_json())
                os.replace(tmp_path, self._state_path)
            except Exception:
                # Rydd opp temp hvis replace feilet
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            log.warning("[SAFETY] Kunne ikke skrive daily_loss_state: %s", e)
